from app.runtime.audit_runner import should_run_audit
from app.runtime.runtime_policy import evaluate_runtime_policy


def test_runtime_policy_keeps_simple_question_lightweight():
    policy = evaluate_runtime_policy(
        user_message="What is my current balance?",
        transactions=[{"amount": 100}],
        monthly_totals=[],
    )

    assert policy.complexity == "simple"
    assert policy.risk_level == "low"
    assert policy.required_specialists == []
    assert policy.audit_required is False
    assert policy.max_deliberation_rounds == 0


def test_runtime_policy_routes_budget_and_spending_to_specialists():
    policy = evaluate_runtime_policy(
        user_message="帮我分析这个月消费，并给下个月预算计划",
        transactions=[{"amount": -100}],
        monthly_totals=[{"month": "2026-06"}],
    )

    assert policy.complexity == "complex"
    assert policy.required_specialists == ["expense_analyst", "budget_analyst"]
    assert policy.audit_required is True
    assert should_run_audit(policy, specialists_used=policy.required_specialists) is True


def test_runtime_policy_flags_risky_market_questions():
    policy = evaluate_runtime_policy(
        user_message="Should I buy this stock for guaranteed returns?",
        transactions=[],
        monthly_totals=[],
    )

    assert policy.complexity == "complex"
    assert policy.risk_level == "high"
    assert policy.audit_required is True
    assert policy.allow_market_context is True
