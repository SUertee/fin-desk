"""Cash-plan API used by the workspace and the CFO runtime."""

from datetime import date

from fastapi import APIRouter, Query

from app.models.cash_plan import CashPlanUpdate
from app.services.cash_plan import build_cash_projection, get_cash_plan, update_cash_plan

router = APIRouter(prefix="/cash-plan", tags=["cash-plan"])


@router.get("/{user_id}")
def read_cash_plan(
    user_id: str,
    as_of: date | None = None,
    horizon_days: int = Query(default=120, ge=1, le=730),
):
    plan = get_cash_plan(user_id)
    return {
        "plan": plan.model_dump(mode="json"),
        "projection": build_cash_projection(plan, as_of=as_of, horizon_days=horizon_days),
    }


@router.put("/{user_id}")
def write_cash_plan(user_id: str, req: CashPlanUpdate):
    plan = update_cash_plan(user_id, req)
    return {
        "plan": plan.model_dump(mode="json"),
        "projection": build_cash_projection(plan),
    }
