"""Authentication service with opaque sessions and bounded login attempts."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from app.auth.password import verify_password
from app.auth.store import create_session_db, get_session_db, revoke_session_db
from app.config.settings import AuthSettings

SESSION_COOKIE = "findesk_session"

_attempt_lock = threading.Lock()
_failed_attempts: deque[float] = deque()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def login(settings: AuthSettings, *, email: str, password: str) -> tuple[str, dict]:
    _enforce_rate_limit(settings)
    valid_email = secrets.compare_digest(email.strip().lower(), settings.email)
    valid_password = verify_password(settings.password_hash, password)
    if not (valid_email and valid_password):
        _record_failure(settings)
        raise PermissionError("Invalid email or password")

    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.session_ttl_seconds
    )
    if not create_session_db(
        token_hash=token_digest(token),
        user_id=settings.user_id,
        email=settings.email,
        csrf_token=csrf_token,
        expires_at=expires_at,
    ):
        raise RuntimeError("Authentication storage is unavailable")
    with _attempt_lock:
        _failed_attempts.clear()
    return token, {
        "user_id": settings.user_id,
        "email": settings.email,
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
