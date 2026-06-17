from app.tools.specialist_tools import (
    build_budget_coach_plan,
    build_controlled_specialist_payloads,
    build_expense_analyst_review,
)


CONTEXT = {
    "profile": {"financial_goals": ["save more"]},
    "expense_snapshot": {
        "transaction_count": 12,
        "income_total": 10000,
        "expense_total": 6800,
        "top_categories": [
            {"category": "Housing", "amount": 4000},
            {"category": "Dining", "amount": 1200},
        ],
        "anomaly_count": 1,
        "anomalies": [{"description": "Unusually large dinner", "amount": -800}],
    },
    "budget_snapshot": {
        "monthly_income": 10000,
        "expense_total": 6800,
        "expense_ratio": 0.68,
        "status": "watch",
        "financial_goals": ["save more"],
    },
}


def test_build_expense_analyst_review_returns_structured_findings():
    review = build_expense_analyst_review(CONTEXT)

    assert review["specialist"] == "expense_analyst"
    assert review["summary"]["transaction_count"] == 12
    assert review["findings"][0]["title"] == "Housing is the largest spending category"
    assert "Housing: 4000" in review["evidence"]
    assert review["confidence"] == 0.75


def test_build_budget_coach_plan_uses_budget_status():
    plan = build_budget_coach_plan(CONTEXT)

    assert plan["specialist"] == "budget_coach"
    assert plan["summary"]["status"] == "watch"
    assert plan["actions"][0]["impact"] == "medium"
    assert "largest flexible category" in plan["recommendations"][0]
    assert plan["limitations"] == []


def test_build_controlled_specialist_payloads_contains_cfo_tools():
    payloads = build_controlled_specialist_payloads(CONTEXT)

    assert set(payloads) == {"expense_analyst_review", "budget_coach_plan"}
    assert payloads["expense_analyst_review"]["specialist"] == "expense_analyst"
    assert payloads["budget_coach_plan"]["specialist"] == "budget_coach"


def test_budget_coach_plan_handles_missing_income():
    plan = build_budget_coach_plan(
        {
            "profile": {},
            "budget_snapshot": {"status": "data_limited", "expense_ratio": None},
            "expense_snapshot": {},
        }
    )

    assert plan["confidence"] == 0.45
    assert plan["limitations"] == [
        "Monthly income is missing, so expense ratio cannot be calculated."
    ]
