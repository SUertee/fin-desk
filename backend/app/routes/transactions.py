"""
/transactions and /analysis-runs endpoints for frontend dashboards.
"""

import calendar
import logging
import re
from datetime import date, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.connectors.postgres.transactions_store import (
    get_latest_analysis_run_db,
    insert_transactions_db,
    list_daily_totals_db,
    list_transactions_db,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ManualTransactionRequest(BaseModel):
    amount: float = Field(gt=0, le=100_000_000)
    direction: Literal["expense", "income"] = "expense"
    entry_type: Literal["expense", "income", "refund", "transfer"] | None = None
    occurred_at: datetime | None = None
    counterparty: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=300)
    category: str = Field(default="other", min_length=1, max_length=80)
    payment_method: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=500)
    meal_tag: Literal["breakfast", "lunch", "dinner"] | None = None
    template_id: str = Field(default="", max_length=80)
    destination_account: str = Field(default="", max_length=100)


@router.post("/transactions/{user_id}", status_code=201)
def create_manual_transaction(user_id: str, payload: ManualTransactionRequest):
    occurred_at = payload.occurred_at or datetime.now().astimezone()
    transaction_date = occurred_at.date().isoformat()
    entry_type = payload.entry_type or payload.direction
    signed_amount = payload.amount if entry_type in {"income", "refund"} else (-payload.amount if entry_type == "expense" else 0)
    external_id = f"manual:{uuid4()}"
    description = payload.description.strip() or payload.counterparty.strip() or (
        {"income": "手工收入", "refund": "手工退款", "transfer": "账户转账"}.get(entry_type, "手工支出")
    )
    transaction = {
        "date": transaction_date,
        "month": transaction_date[:7],
        "description": description,
        "counterparty": payload.counterparty.strip(),
        "amount": signed_amount,
        "gross_amount": payload.amount,
        "currency": "CNY",
        "direction": "income" if entry_type in {"income", "refund"} else entry_type,
        "type": f"manual_{entry_type}",
        "category": "transfer" if entry_type == "transfer" else payload.category,
        "status": "awaiting_statement",
        "payment_method": payload.payment_method.strip(),
        "external_id": external_id,
        "source": "manual",
        "source_format": "manual_entry",
        "note": payload.note.strip(),
        "raw": {
            "manual": {
                "occurred_at": occurred_at.isoformat(),
                "meal_tag": payload.meal_tag,
                "template_id": payload.template_id.strip(),
                "entry_type": entry_type,
                "entered_amount": payload.amount,
                "destination_account": payload.destination_account.strip(),
                "reconciliation_status": "awaiting_statement",
            }
        },
    }
    if not insert_transactions_db(user_id, [transaction]):
        raise HTTPException(status_code=500, detail="Failed to save transaction")
    return {"ok": True, "item": {"user_id": user_id, **transaction}}


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
