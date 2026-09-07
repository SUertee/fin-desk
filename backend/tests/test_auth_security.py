"""Security boundary tests for the browser login flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.auth.password import hash_password, verify_password
from app.config.settings import get_settings
from app.main import app


def _enable_auth(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_USER_ID", "demo")
    monkeypatch.setenv("AUTH_EMAIL", "owner@example.com")
    monkeypatch.setenv("AUTH_PASSWORD_HASH", hash_password("correct horse battery"))
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_settings.cache_clear()


def test_argon2_password_hash_never_contains_plaintext():
    password_hash = hash_password("correct horse battery")
    assert password_hash.startswith("$argon2")
    assert "correct horse battery" not in password_hash
    assert verify_password(password_hash, "correct horse battery") is True
    assert verify_password(password_hash, "wrong password") is False


def test_private_routes_reject_missing_session(monkeypatch):
    _enable_auth(monkeypatch)
    try:
        client = TestClient(app)
        assert client.get("/health").status_code == 200
        response = client.get("/profile/demo")
        assert response.status_code == 401
        assert response.json()["error"] == "Authentication required"
    finally:
        get_settings.cache_clear()


def test_session_requires_csrf_for_mutations(monkeypatch):
    _enable_auth(monkeypatch)
    session = {
        "user_id": "demo",
        "email": "owner@example.com",
        "csrf_token": "csrf-secret",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    monkeypatch.setattr("app.auth.middleware.resolve_session", lambda _token: session)
    try:
        client = TestClient(app)
        client.cookies.set("findesk_session", "opaque-token")
        blocked = client.put("/profile/demo", json={"name": "Owner"})
        assert blocked.status_code == 403

        allowed = client.put(
            "/profile/demo",
            json={"name": "Owner"},
            headers={"X-CSRF-Token": "csrf-secret"},
        )
        assert allowed.status_code != 403
    finally:
        get_settings.cache_clear()


def test_session_cannot_cross_user_scope(monkeypatch):
    _enable_auth(monkeypatch)
    session = {
        "user_id": "demo",
        "email": "owner@example.com",
        "csrf_token": "csrf-secret",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    monkeypatch.setattr("app.auth.middleware.resolve_session", lambda _token: session)
    try:
        client = TestClient(app)
        client.cookies.set("findesk_session", "opaque-token")
        assert client.get("/profile/another-user").status_code == 403
        assert client.get("/statement-imports?user_id=another-user").status_code == 403
        response = client.post(
            "/office/sessions",
            json={"user_id": "another-user", "title": "blocked"},
            headers={"X-CSRF-Token": "csrf-secret"},
        )
        assert response.status_code == 403

        own_upload = client.post(
            "/statement-imports/upload",
            data={"user_id": "demo"},
            files={"file": ("empty.csv", b"not,a,statement", "text/csv")},
            headers={"X-CSRF-Token": "csrf-secret"},
        )
        assert own_upload.status_code not in {401, 403, 422}
    finally:
        get_settings.cache_clear()


def test_login_sets_httponly_strict_cookie(monkeypatch):
    _enable_auth(monkeypatch)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    monkeypatch.setattr(
        "app.routes.auth.login",
        lambda _settings, **_credentials: (
            "opaque-token",
            {
                "user_id": "demo",
                "email": "owner@example.com",
                "csrf_token": "csrf-secret",
                "expires_at": expires_at,
            },
        ),
    )
    try:
        response = TestClient(app).post(
            "/auth/login",
            json={"email": "owner@example.com", "password": "valid-password"},
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        assert response.json()["user"]["id"] == "demo"
    finally:
        get_settings.cache_clear()
