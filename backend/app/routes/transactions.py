"""
/transactions and /analysis-runs endpoints for frontend dashboards.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.repositories.transactions_repo import get_latest_analysis_run_db, list_transactions_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/transactions/{user_id}")
def get_transactions(user_id: str, limit: int = 500):
    try:
        return {"user_id": user_id, "items": list_transactions_db(user_id, limit)}
    except Exception:
        logger.exception("Failed to get transactions for user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to retrieve transactions"})


@router.get("/analysis-runs/latest/{user_id}")
def get_latest_analysis_run(user_id: str):
    try:
        result = get_latest_analysis_run_db(user_id)
        return result if result else {"ok": True, "data": None}
    except Exception:
        logger.exception("Failed to get analysis run for user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to retrieve analysis run"})
