from app.runtime.orchestration.finance_runtime import FinanceRuntime
from app.runtime.policy.audit_runner import should_run_audit
from app.runtime.policy.runtime_policy import evaluate_runtime_policy


def _policy(*capability_ids: str):
    runtime = FinanceRuntime()
    return evaluate_runtime_policy(list(capability_ids), runtime.capability_catalog)


def test_low_risk_tool_stays_simple_without_audit():
    policy = _policy("finance.context")

    assert policy.complexity == "simple"
    assert policy.risk_level == "low"
    assert policy.required_specialists == []
    assert policy.audit_required is False
    assert policy.max_deliberation_rounds == 0


def test_specialist_requests_require_audit():
    policy = _policy("finance.expense_review", "finance.budget_coaching")

    assert policy.complexity == "moderate"
    assert policy.required_specialists == ["expense_analyst", "budget_coach"]
    assert policy.audit_required is True
    assert should_run_audit(policy, specialists_used=policy.required_specialists) is True


def test_market_context_is_enabled_only_by_explicit_capability():
    unrelated = _policy("finance.expense_review")
    market = _policy("market.context_review")

    assert unrelated.allow_market_context is False
    assert market.allow_market_context is True
    assert market.risk_level == "medium"
    assert market.required_specialists == ["market_context"]
    assert market.audit_required is True


def test_investment_research_is_a_distinct_medium_risk_specialist():
    policy = _policy("investment.research_review")

    assert policy.required_specialists == ["investment_research"]
    assert "market_context" not in policy.required_specialists
    assert policy.risk_level == "medium"
    assert policy.audit_required is True


def test_unknown_capability_is_rejected_before_execution():
    runtime = FinanceRuntime()

    try:
        evaluate_runtime_policy(["unknown.capability"], runtime.capability_catalog)
    except ValueError as exc:
        assert "Unknown capability id" in str(exc)
    else:
        raise AssertionError("unknown capability must be rejected")
