"""
/transactions and /analysis-runs endpoints for frontend dashboards.
"""

import calendar
import logging
import re
from datetime import date

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.connectors.postgres.transactions_store import (
    get_latest_analysis_run_db,
    list_daily_totals_db,
    list_transactions_db,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("/transactions/daily/{user_id}")
def get_daily_totals(user_id: str, month: str):
    if not _MONTH_PATTERN.match(month):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "month must be formatted YYYY-MM"},
        )
    try:
        year, month_number = int(month[:4]), int(month[5:7])
        last_day = calendar.monthrange(year, month_number)[1]
        date_from = date(year, month_number, 1).isoformat()
        date_to = date(year, month_number, last_day).isoformat()
        days = list_daily_totals_db(user_id, date_from, date_to)
        return {
            "user_id": user_id,
            "month": month,
            "days": days,
            "totals": {
                "expense": round(sum(d["expense"] for d in days), 2),
                "income": round(sum(d["income"] for d in days), 2),
                "count": sum(d["count"] for d in days),
            },
        }
    except Exception:
        logger.exception("Failed to get daily totals for user=%s", user_id)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to retrieve daily totals"},
        )


@router.get("/transactions/{user_id}")
def get_transactions(
    user_id: str,
    limit: int = 500,
    date_from: str | None = None,
    date_to: str | None = None,
):
    try:
        return {
            "user_id": user_id,
            "items": list_transactions_db(
                user_id, limit, date_from=date_from, date_to=date_to
            ),
        }
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
