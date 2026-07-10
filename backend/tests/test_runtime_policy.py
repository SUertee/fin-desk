from app.runtime.policy.audit_runner import should_run_audit
from app.runtime.policy.runtime_policy import evaluate_runtime_policy


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
    assert policy.required_specialists == ["expense_analyst", "budget_coach"]
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
    # Market context requires the explicit config gate, not just intent.
    assert policy.allow_market_context is False
    assert "market_context" not in policy.required_specialists


def test_market_context_gate_off_never_selects_specialist(monkeypatch):
    monkeypatch.delenv("MARKET_CONTEXT_ENABLED", raising=False)

    policy = evaluate_runtime_policy(
        user_message="最近利率新闻对我的预算有什么影响？",
        transactions=[{"amount": -100}],
        monthly_totals=[],
    )

    assert policy.allow_market_context is False
    assert "market_context" not in policy.required_specialists


def test_market_context_gate_on_with_intent_selects_alongside_audit(monkeypatch):
    monkeypatch.setenv("MARKET_CONTEXT_ENABLED", "1")

    policy = evaluate_runtime_policy(
        user_message="市场新闻里利率变化对我有什么影响？",
        transactions=[{"amount": -100}],
        monthly_totals=[],
    )

    assert policy.allow_market_context is True
    assert "market_context" in policy.required_specialists
    assert policy.audit_required is True  # alongside, never instead of, audit


def test_market_context_gate_on_without_intent_stays_out(monkeypatch):
    monkeypatch.setenv("MARKET_CONTEXT_ENABLED", "1")

    policy = evaluate_runtime_policy(
        user_message="这个月消费怎么样？",
        transactions=[{"amount": -100}],
        monthly_totals=[],
    )

    assert policy.allow_market_context is False
    assert "market_context" not in policy.required_specialists
