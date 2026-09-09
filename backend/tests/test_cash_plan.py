from datetime import date

from app.models.cash_plan import CashPlan, CashPlanEntry
from app.services.cash_plan import build_cash_projection


def test_projection_accounts_for_daily_budget_and_due_dates_before_payday():
    plan = CashPlan(
        user_id="demo",
        cash_balance=1800,
        daily_budget=35,
        entries=[
            CashPlanEntry(name="花呗", kind="debt", amount=439.92, due_date=date(2026, 9, 8), outstanding_balance=2917.16),
            CashPlanEntry(name="工资", kind="income", amount=5850, due_date=date(2026, 9, 15), recurrence="monthly"),
        ],
    )

    projection = build_cash_projection(plan, as_of=date(2026, 9, 7), horizon_days=10)

    assert projection["next_income_date"] == "2026-09-15"
    assert projection["total_debt"] == 2917.16
    assert projection["safe_to_spend_until_next_income"] == 1080.08
    assert projection["events"][0]["running_balance"] == 1325.08
    assert projection["events"][1]["running_balance"] == 6930.08


def test_projection_uses_a_different_amount_after_first_monthly_payment():
    plan = CashPlan(
        user_id="demo",
        entries=[
            CashPlanEntry(
                name="账单分期", kind="debt", amount=439.92,
                recurring_amount=204.98, due_date=date(2026, 9, 8),
                recurrence="monthly", remaining_occurrences=3,
            )
        ],
    )

    projection = build_cash_projection(plan, as_of=date(2026, 9, 7), horizon_days=70)

    assert [event["amount"] for event in projection["events"]] == [-439.92, -204.98, -204.98]
