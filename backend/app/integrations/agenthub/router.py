"""Agent Hub serve-mode endpoints (protocol 0.1, read-only)."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.integrations.agenthub import providers

logger = logging.getLogger(__name__)
router = APIRouter(tags=["agent-hub"])


def _check_token(request: Request) -> None:
    token = os.environ.get("AGENTHUB_TOKEN")
    if not token:
        return
    if request.headers.get("authorization") != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Invalid or missing token")


def _guarded(payload_builder, *args: Any) -> dict[str, Any]:
    try:
        return payload_builder(*args)
    except Exception:
        logger.exception("Agent Hub provider failed")
        raise HTTPException(status_code=503, detail="Provider unavailable")


@router.get("/agent-gateway/manifest")
def get_manifest(request: Request) -> dict[str, Any]:
    _check_token(request)
    return _guarded(providers.build_manifest)


@router.get("/agent-gateway/roster")
def get_roster(request: Request) -> dict[str, Any]:
    _check_token(request)
    return _guarded(providers.build_roster)


@router.get("/agent-gateway/state")
async def get_state(request: Request) -> dict[str, Any]:
    _check_token(request)
    try:
        return await providers.build_state()
    except Exception:
        logger.exception("Agent Hub state provider failed")
        raise HTTPException(status_code=503, detail="Provider unavailable")


@router.get("/agent-gateway/runs")
def get_runs(
    request: Request,
    since: str | None = None,
    user_id: str = providers.DEFAULT_USER_ID,
    limit: int = 20,
) -> dict[str, Any]:
    _check_token(request)
    try:
        return providers.build_runs(since, user_id=user_id, limit=limit)
    except Exception:
        logger.exception("Agent Hub runs provider failed")
        raise HTTPException(status_code=503, detail="Provider unavailable")


@router.get("/.well-known/agent-card.json")
def get_agent_card() -> dict[str, Any]:
    return _guarded(providers.build_agent_card)
