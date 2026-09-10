"""Cash-plan persistence and deterministic cash runway projections."""

import calendar
from datetime import date, datetime, timedelta, timezone

from app.connectors.postgres.cash_plan_store import (
    CashPlanStorageError,
    get_cash_plan_db,
    save_cash_plan_db,
)
from app.models.cash_plan import CashPlan, CashPlanEntry, CashPlanUpdate

def get_cash_plan(user_id: str) -> CashPlan | None:
    """Return a configured plan, keeping 'not configured' distinct from failure."""
    return get_cash_plan_db(user_id)


def update_cash_plan(user_id: str, req: CashPlanUpdate) -> CashPlan:
    plan = CashPlan(
        user_id=user_id,
        currency=req.currency.upper(),
        cash_balance=req.cash_balance,
        daily_budget=req.daily_budget,
        monthly_budget=req.monthly_budget,
        entries=req.entries,
        updated_at=datetime.now(timezone.utc),
    )
    save_cash_plan_db(plan)
    return plan


def _add_months(value: date, months: int) -> date:
    target = value.month - 1 + months
    year = value.year + target // 12
    month = target % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _occurrences(entry: CashPlanEntry, end: date) -> list[tuple[date, float]]:
    if entry.status != "active":
        return []
    count = entry.remaining_occurrences or (1 if entry.recurrence == "once" else 240)
    result: list[tuple[date, float]] = []
    for index in range(count):
        when = entry.due_date if index == 0 else _add_months(entry.due_date, index)
        if when > end:
            break
        amount = entry.amount if index == 0 else (entry.recurring_amount or entry.amount)
        result.append((when, amount))
        if entry.recurrence == "once":
            break
    return result


def build_cash_projection(
    plan: CashPlan, *, as_of: date | None = None, horizon_days: int = 120
) -> dict:
    start = as_of or date.today()
    end = start + timedelta(days=max(1, min(horizon_days, 730)))
    events: list[dict] = []
    for entry in plan.entries:
        for when, raw_amount in _occurrences(entry, end):
            if when < start:
                continue
            signed = raw_amount if entry.kind == "income" else -raw_amount
            events.append(
                {
                    "entry_id": entry.id,
                    "name": entry.name,
                    "kind": entry.kind,
                    "date": when.isoformat(),
                    "amount": round(signed, 2),
                    "essential": entry.essential,
                }
            )
    events.sort(key=lambda item: (item["date"], 0 if item["amount"] < 0 else 1, item["name"]))

    balance = plan.cash_balance
    minimum = balance
    cursor = start
    for event in events:
        event_date = date.fromisoformat(event["date"])
        days = max(0, (event_date - cursor).days)
        balance -= days * plan.daily_budget
        balance += event["amount"]
        minimum = min(minimum, balance)
        event["running_balance"] = round(balance, 2)
        cursor = event_date
    balance -= max(0, (end - cursor).days) * plan.daily_budget
    minimum = min(minimum, balance)

    next_income = next((event for event in events if event["kind"] == "income"), None)
    if next_income:
        payday = date.fromisoformat(next_income["date"])
        committed = sum(-event["amount"] for event in events if event["amount"] < 0 and date.fromisoformat(event["date"]) <= payday)
        living = max(0, (payday - start).days) * plan.daily_budget
        safe_to_spend = max(0, plan.cash_balance - committed - living)
    else:
        safe_to_spend = max(0, plan.cash_balance)

    debt_total = sum(
        entry.outstanding_balance or 0
        for entry in plan.entries
        if entry.kind == "debt" and entry.status == "active"
    )
    return {
        "as_of": start.isoformat(),
        "horizon_end": end.isoformat(),
        "currency": plan.currency,
        "current_cash": round(plan.cash_balance, 2),
        "total_debt": round(debt_total, 2),
        "next_income_date": next_income["date"] if next_income else None,
        "safe_to_spend_until_next_income": round(safe_to_spend, 2),
        "minimum_projected_balance": round(minimum, 2),
        "funding_gap": round(max(0, -minimum), 2),
        "ending_balance": round(balance, 2),
        "events": events,
    }


def cash_plan_context(user_id: str) -> dict:
    try:
        plan = get_cash_plan(user_id)
    except CashPlanStorageError:
        return {
            "available": False,
            "configured": False,
            "plan": None,
            "projection": None,
        }
    if plan is None:
        return {
            "available": True,
            "configured": False,
            "plan": None,
            "projection": None,
        }
    return {
        "available": True,
        "configured": True,
        "plan": plan.model_dump(mode="json"),
        "projection": build_cash_projection(plan),
    }
