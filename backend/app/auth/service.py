"""Authentication service with opaque sessions and bounded login attempts."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from app.auth.password import hash_password, verify_password
from app.auth.store import (
    create_owner_db,
    create_session_db,
    get_owner_by_email_db,
    get_session_db,
    owner_exists_db,
    revoke_session_db,
)
from app.config.settings import AuthSettings

SESSION_COOKIE = "findesk_session"
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-findesk-owner-password")

_attempt_lock = threading.Lock()
_failed_attempts: deque[float] = deque()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def login(settings: AuthSettings, *, email: str, password: str) -> tuple[str, dict]:
    _enforce_rate_limit(settings)
    normalized_email = email.strip().lower()
    owner = get_owner_by_email_db(normalized_email)
    if (
        owner is None
        and settings.email
        and settings.password_hash
        and secrets.compare_digest(normalized_email, settings.email)
    ):
        owner = {
            "user_id": settings.user_id,
            "email": settings.email,
            "password_hash": settings.password_hash,
        }
    candidate_hash = owner["password_hash"] if owner else _DUMMY_PASSWORD_HASH
    valid_password = verify_password(candidate_hash, password)
    if owner is None or not valid_password:
        _record_failure(settings)
        raise PermissionError("Invalid email or password")

    return _create_session(
        settings,
        user_id=owner["user_id"],
        email=owner["email"],
    )


def registration_status(settings: AuthSettings) -> bool:
    if not settings.enabled or not settings.allow_initial_registration:
        return False
    exists = owner_exists_db()
    if exists is None:
        raise RuntimeError("Authentication storage is unavailable")
    return not exists


def register_owner(
    settings: AuthSettings, *, email: str, password: str, setup_token: str
) -> tuple[str, dict]:
    _enforce_rate_limit(settings)
    if not registration_status(settings):
        raise FileExistsError("Initial registration is closed")
    supplied_hash = token_digest(setup_token.strip())
    if not secrets.compare_digest(supplied_hash, settings.setup_token_hash):
        _record_failure(settings)
        raise PermissionError("Invalid setup code")
    normalized_email = email.strip().lower()
    if not create_owner_db(
        user_id=settings.user_id,
        email=normalized_email,
        password_hash=hash_password(password),
    ):
        raise FileExistsError("Initial registration is closed")
    return _create_session(settings, user_id=settings.user_id, email=normalized_email)


def _create_session(
    settings: AuthSettings, *, user_id: str, email: str
) -> tuple[str, dict]:
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.session_ttl_seconds
    )
    if not create_session_db(
        token_hash=token_digest(token),
        user_id=user_id,
        email=email,
        csrf_token=csrf_token,
        expires_at=expires_at,
    ):
        raise RuntimeError("Authentication storage is unavailable")
    with _attempt_lock:
        _failed_attempts.clear()
    return token, {
        "user_id": user_id,
        "email": email,
        "csrf_token": csrf_token,
        "expires_at": expires_at,
    }


def resolve_session(token: str) -> dict | None:
    if not token:
        return None
    return get_session_db(token_digest(token))


def logout(token: str) -> None:
    if token:
        revoke_session_db(token_digest(token))


def _enforce_rate_limit(settings: AuthSettings) -> None:
    now = time.monotonic()
    cutoff = now - settings.login_window_seconds
    with _attempt_lock:
        while _failed_attempts and _failed_attempts[0] < cutoff:
            _failed_attempts.popleft()
        if len(_failed_attempts) >= settings.login_attempt_limit:
            raise TimeoutError("Too many login attempts. Try again later.")


def _record_failure(settings: AuthSettings) -> None:
    now = time.monotonic()
    cutoff = now - settings.login_window_seconds
    with _attempt_lock:
        while _failed_attempts and _failed_attempts[0] < cutoff:
            _failed_attempts.popleft()
        _failed_attempts.append(now)
