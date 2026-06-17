"""
/profile endpoints - User profile management.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models.user import ProfileUpdateRequest
from app.services.user_store import get_profile, update_profile

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/profile/{user_id}")
def get_user_profile(user_id: str):
    try:
        p = get_profile(user_id)
        return p.model_dump()
    except Exception:
        logger.exception("Failed to get profile for user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to retrieve profile"})


@router.put("/profile/{user_id}")
def update_user_profile(user_id: str, req: ProfileUpdateRequest):
    try:
        p = update_profile(user_id, req)
        return p.model_dump()
    except Exception:
        logger.exception("Failed to update profile for user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to update profile"})
