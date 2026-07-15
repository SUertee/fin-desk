"""Finance-facing AI Cost Explorer endpoints."""

from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.connectors.postgres.exchange_rate_store import get_exchange_rate_snapshot_db
from app.connectors.postgres.run_ledger_store import list_agent_run_cost_records_db
from app.models.cost_explorer import AICostOverview
from app.models.costing import MoneyAmount, normalize_currency
from app.services.ai_cost_analytics import AICostAnalyticsService
from app.services.user_store import get_profile


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/costs", tags=["costs"])
_service = AICostAnalyticsService(
    records_reader=list_agent_run_cost_records_db,
    exchange_rate_lookup=get_exchange_rate_snapshot_db,
)


def _default_period() -> tuple[date, date]:
    today = date.today()
    return today.replace(day=1), today.replace(
        day=monthrange(today.year, today.month)[1]
    )


@router.get("/ai/{user_id}/overview", response_model=AICostOverview)
def get_ai_cost_overview(
    user_id: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    reporting_currency: str | None = Query(default=None),
):
    default_from, default_to = _default_period()
    start = date_from or default_from
    end = date_to or default_to
    if start > end:
        raise HTTPException(status_code=400, detail="date_from must be on or before date_to")
    if (end - start).days > 365:
        raise HTTPException(status_code=400, detail="AI cost range cannot exceed 366 days")

    profile = get_profile(user_id)
    try:
        selected_currency = normalize_currency(
            reporting_currency or profile.cost_preferences.reporting_currency
        )
        budget = None
        if profile.cost_preferences.monthly_ai_budget is not None:
            budget = MoneyAmount(
                amount=profile.cost_preferences.monthly_ai_budget,
                currency=profile.cost_preferences.reporting_currency,
            )
        return _service.overview(
            user_id=user_id,
            date_from=start,
            date_to=end,
            reporting_currency=selected_currency,
            monthly_budget=budget,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Failed to load AI costs for user=%s", user_id)
        raise HTTPException(status_code=503, detail="AI cost data is unavailable") from exc

