"""Bind every user-scoped request to the authenticated session owner."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.config.settings import get_settings


async def enforce_user_scope(request: Request) -> None:
    settings = get_settings()
    if not settings.auth.enabled or request.url.path in {"/health", "/auth/login"}:
        return

    authenticated_user = getattr(request.state, "auth_user_id", "")
    if not authenticated_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    candidates: list[str] = []
    path_user = request.path_params.get("user_id")
    query_user = request.query_params.get("user_id")
    if path_user:
        candidates.append(path_user)
    if query_user:
        candidates.append(query_user)

    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("user_id"):
            candidates.append(str(payload["user_id"]))
    elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        form_user = form.get("user_id")
        if isinstance(form_user, str) and form_user:
            candidates.append(form_user)

    if any(candidate != authenticated_user for candidate in candidates):
        raise HTTPException(status_code=403, detail="User scope mismatch")
