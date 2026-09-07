"""Single-user authentication endpoints."""

from __future__ import annotations

import re

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.auth.service import (
    SESSION_COOKIE,
    login,
    logout,
    register_owner,
    registration_status,
)
from app.config.settings import get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("invalid email")
        return normalized


class RegisterRequest(LoginRequest):
    password: str = Field(min_length=12, max_length=512)
    setup_token: str = Field(min_length=16, max_length=512)


def _session_payload(session: dict) -> dict:
    return {
        "authenticated": True,
        "user": {"id": session["user_id"], "email": session["email"]},
        "csrf_token": session["csrf_token"],
        "expires_at": session.get("expires_at"),
    }


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.auth.session_ttl_seconds,
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite="strict",
        path="/",
    )


@router.get("/status")
def status_route():
    try:
        setup_required = registration_status(get_settings().auth)
    except RuntimeError:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "Authentication service unavailable"},
        )
    return {"setup_required": setup_required}


@router.post("/register")
def register_route(payload: RegisterRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    try:
        token, session = register_owner(
            settings.auth,
            email=payload.email,
            password=payload.password,
            setup_token=payload.setup_token,
        )
    except PermissionError:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "Invalid setup code"},
        )
    except FileExistsError:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": "Initial registration is closed"},
        )
    except (RuntimeError, ValueError):
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "Authentication service unavailable"},
        )
    _set_session_cookie(response, token)
    return _session_payload(session)


@router.post("/login")
def login_route(payload: LoginRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    if not settings.auth.enabled:
        return _session_payload(
            {
                "user_id": settings.default_user_id,
                "email": settings.auth.email or "local@findesk.test",
                "csrf_token": "local-development",
            }
        )
    try:
        token, session = login(
            settings.auth, email=str(payload.email), password=payload.password
        )
    except PermissionError:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "Invalid email or password"},
        )
    except TimeoutError as exc:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(settings.auth.login_window_seconds)},
            content={"ok": False, "error": str(exc)},
        )
    except RuntimeError:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "Authentication service unavailable"},
        )
    _set_session_cookie(response, token)
    return _session_payload(session)


@router.get("/session")
def session_route(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    if not settings.auth.enabled:
        return _session_payload(
            {
                "user_id": settings.default_user_id,
                "email": settings.auth.email or "local@findesk.test",
                "csrf_token": "local-development",
            }
        )
    return _session_payload(request.state.auth_session)


@router.post("/logout")
def logout_route(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    if settings.auth.enabled:
        logout(request.cookies.get(SESSION_COOKIE, ""))
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite="strict",
        path="/",
    )
    return {"ok": True}
