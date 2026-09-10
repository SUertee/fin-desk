"""Cash-plan API used by the workspace and the CFO runtime."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.connectors.postgres.cash_plan_store import CashPlanStorageError
from app.models.cash_plan import CashPlanUpdate
from app.services.cash_plan import build_cash_projection, get_cash_plan, update_cash_plan

router = APIRouter(prefix="/cash-plan", tags=["cash-plan"])


@router.get("/{user_id}")
def read_cash_plan(
    user_id: str,
    as_of: date | None = None,
    horizon_days: int = Query(default=120, ge=1, le=730),
):
    try:
        plan = get_cash_plan(user_id)
    except CashPlanStorageError as exc:
        raise HTTPException(status_code=503, detail="Cash plan is temporarily unavailable") from exc
    if plan is None:
        return {"configured": False, "plan": None, "projection": None}
    return {
        "configured": True,
        "plan": plan.model_dump(mode="json"),
        "projection": build_cash_projection(plan, as_of=as_of, horizon_days=horizon_days),
    }


@router.put("/{user_id}")
def write_cash_plan(user_id: str, req: CashPlanUpdate):
    try:
        plan = update_cash_plan(user_id, req)
    except CashPlanStorageError as exc:
        raise HTTPException(status_code=503, detail="Cash plan could not be saved") from exc
    return {
        "configured": True,
        "plan": plan.model_dump(mode="json"),
        "projection": build_cash_projection(plan),
    }
