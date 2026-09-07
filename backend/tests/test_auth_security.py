"""Security boundary tests for the browser login flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.auth.password import hash_password, verify_password
from app.auth.service import login, register_owner, token_digest
from app.config.settings import AuthSettings, get_settings
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


def test_initial_registration_is_token_gated_and_one_time(monkeypatch):
    setup_token = "one-time-setup-token-value"
    settings = AuthSettings(
        enabled=True,
        user_id="demo",
        allow_initial_registration=True,
        setup_token_hash=token_digest(setup_token),
    )
    owner_exists = False
    monkeypatch.setattr(
        "app.auth.service.owner_exists_db", lambda: owner_exists
    )
    monkeypatch.setattr("app.auth.service.create_owner_db", lambda **_values: True)
    monkeypatch.setattr("app.auth.service.create_session_db", lambda **_values: True)

    token, session = register_owner(
        settings,
        email="owner@example.com",
        password="correct horse battery",
        setup_token=setup_token,
    )
    assert token
    assert session["email"] == "owner@example.com"

    owner_exists = True
    try:
        register_owner(
            settings,
            email="second@example.com",
            password="correct horse battery",
            setup_token=setup_token,
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("second owner registration must be rejected")


def test_login_does_not_accept_correct_password_for_wrong_email(monkeypatch):
    settings = AuthSettings(
        enabled=True,
        user_id="demo",
        email="owner@example.com",
        password_hash=hash_password("correct horse battery"),
    )
    monkeypatch.setattr("app.auth.service.get_owner_by_email_db", lambda _email: None)
    try:
        login(
            settings,
            email="attacker@example.com",
            password="correct horse battery",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("email must be verified together with the password")
