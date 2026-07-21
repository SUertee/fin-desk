from app.models.runtime import RuntimePolicyResult
from app.runtime.execution.context import AgentContext
from app.runtime.execution.planner import build_execution_plan
from app.tools.investment_research_tools import extract_instrument_reference


def test_extracts_explicit_stock_and_etf_symbols_only():
    assert extract_instrument_reference("请分析股票 AAPL") == ("AAPL", "equity")
    assert extract_instrument_reference("compare ETF QQQ") == ("QQQ", "etf")
    assert extract_instrument_reference("看看 $MSFT 的风险") == ("MSFT", "equity")
    assert extract_instrument_reference("帮我看看苹果公司") is None


def test_investment_specialist_plan_fetches_bounded_research_before_handoff():
    context = AgentContext(
        request_id="req-1",
        user_id="demo",
        entrypoint="chat",
        message="请分析股票 AAPL",
    )
    policy = RuntimePolicyResult(
        complexity="complex",
        risk_level="high",
        required_specialists=["investment_research"],
        audit_required=True,
        max_tool_calls=10,
    )

    plan = build_execution_plan(context, policy)

    assert "investment.research_context" in plan.tool_capability_ids
    assert plan.handoff_capability_ids == [
        "investment.research_review",
        "finance.audit_review",
    ]
    tool_index = next(
        index
        for index, step in enumerate(plan.steps)
        if step.capability_id == "investment.research_context"
    )
    handoff_index = next(
        index
        for index, step in enumerate(plan.steps)
        if step.step_type == "handoff"
        and step.capability_id == "investment.research_review"
    )
    assert tool_index < handoff_index
