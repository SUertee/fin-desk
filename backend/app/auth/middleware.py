"""Fail-closed cookie authentication and CSRF protection."""

from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

from app.auth.service import SESSION_COOKIE, resolve_session
from app.config.settings import get_settings

PUBLIC_PATHS = {"/health", "/auth/login"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def authentication_middleware(request: Request, call_next):
    settings = get_settings()
    if not settings.auth.enabled:
        request.state.auth_user_id = settings.default_user_id
        return await call_next(request)

    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    session = resolve_session(request.cookies.get(SESSION_COOKIE, ""))
    if session is None:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "Authentication required"},
        )

    request.state.auth_user_id = session["user_id"]
    request.state.auth_session = session
    if request.method not in SAFE_METHODS:
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not secrets.compare_digest(supplied, session["csrf_token"]):
            return JSONResponse(
                status_code=403,
                content={"ok": False, "error": "Invalid CSRF token"},
            )
    return await call_next(request)
