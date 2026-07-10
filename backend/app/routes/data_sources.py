"""Data-source status endpoints for Settings."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.data_sources import get_data_source_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("/status/{user_id}")
def get_user_data_source_status(user_id: str):
    try:
        return get_data_source_status(user_id)
    except Exception:
        logger.exception("Failed to get data-source status for user=%s", user_id)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to retrieve data-source status"},
        )
