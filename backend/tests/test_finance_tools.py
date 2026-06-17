from app.tools.finance_tools import (
    build_budget_snapshot,
    build_expense_snapshot,
    build_finance_context_payload,
)


TRANSACTIONS = [
    {
        "date": "2026-05-01",
        "month": "2026-05",
        "description": "Salary",
        "category": "Income",
        "amount": 20000,
        "currency": "CNY",
        "is_duplicate": False,
    },
    {
        "date": "2026-05-02",
        "month": "2026-05",
        "description": "Restaurant A",
        "category": "Dining",
        "amount": -300,
        "currency": "CNY",
        "is_duplicate": False,
    },
    {
        "date": "2026-05-03",
        "month": "2026-05",
        "description": "Rent",
        "category": "Housing",
        "amount": -5000,
        "currency": "CNY",
        "is_duplicate": False,
    },
    {
        "date": "2026-05-03",
        "month": "2026-05",
        "description": "Rent duplicate",
        "category": "Housing",
        "amount": -5000,
        "currency": "CNY",
        "is_duplicate": True,
    },
]


def test_build_expense_snapshot_excludes_duplicates():
    snapshot = build_expense_snapshot(TRANSACTIONS, [])

    assert snapshot["transaction_count"] == 3
    assert snapshot["expense_total"] == 5300
    assert snapshot["income_total"] == 20000
    assert snapshot["net_total"] == 14700
    assert snapshot["top_categories"][0]["category"] == "Housing"


def test_build_budget_snapshot_uses_monthly_income():
    snapshot = build_budget_snapshot(
        {"monthly_income": 20000, "financial_goals": ["save more"]},
        TRANSACTIONS,
        [],
    )

    assert snapshot["monthly_income"] == 20000
    assert snapshot["expense_ratio"] == 0.265
    assert snapshot["status"] == "good"


def test_build_finance_context_payload_limits_transactions():
    payload = build_finance_context_payload(
        user_id="demo",
        profile={"name": "Demo", "monthly_income": 20000},
        transactions=TRANSACTIONS,
        monthly_totals=[],
        chat_history=[{"role": "user", "content": "hello"}],
    )

    assert payload["user_id"] == "demo"
    assert payload["profile"]["name"] == "Demo"
    assert len(payload["transactions_sample"]) == 3
    assert payload["expense_snapshot"]["expense_total"] == 5300
