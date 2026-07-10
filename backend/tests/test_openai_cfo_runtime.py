from types import SimpleNamespace

import pytest

from app.runtime.llm.openai_cfo_runtime import OpenAICFORuntime
from app.tools.openai_finance_tools import build_openai_finance_tool_payloads


CONTEXT = {
    "user_id": "demo",
    "message": "How am I doing this month?",
    "profile": {"name": "Demo"},
    "expense_snapshot": {
        "transaction_count": 8,
        "expense_total": 1200,
        "income_total": 5000,
        "net_total": 3800,
        "anomaly_count": 1,
        "anomalies": [{"description": "Large dinner", "amount": -300}],
    },
    "budget_snapshot": {"status": "good", "expense_ratio": 0.24},
    "monthly_totals": [{"month": "2026-06", "net": 3800}],
    "transactions_sample": [{"amount": -100, "category": "Dining"}],
    "chat_history": [],
    "runtime_policy": {
        "complexity": "moderate",
        "risk_level": "low",
        "required_specialists": ["expense_analyst"],
        "audit_required": True,
    },
}


@pytest.mark.asyncio
async def test_openai_runtime_requires_api_key_without_injected_runner(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = OpenAICFORuntime(
        agent_factory=lambda tools: "agent",
        tool_builder=lambda context: [],
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        await runtime.run(CONTEXT)


@pytest.mark.asyncio
async def test_openai_runtime_uses_injected_runner_and_normalizes_output(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeRunner:
        async def run(self, agent, user_input, max_turns, hooks):
            assert agent == "fake-agent"
            assert max_turns == 6
            assert hooks is not None
            assert "How am I doing this month?" in user_input
            tool = SimpleNamespace(name="consult_expense_analyst")
            await hooks.on_tool_start(
                SimpleNamespace(tool_name="consult_expense_analyst"),
                SimpleNamespace(name="Finance CFO"),
                tool,
            )
            await hooks.on_tool_end(
                SimpleNamespace(tool_name="consult_expense_analyst"),
                SimpleNamespace(name="Finance CFO"),
                tool,
                {"ok": True},
            )
            return SimpleNamespace(
                final_output=(
                    "Your cash flow is healthy.\n"
                    '{"audit": {"confidence": 0.8, "status": "verified", "warnings": []}}'
                ),
                new_items=[
                    SimpleNamespace(
                        type="tool_call_item",
                        agent=SimpleNamespace(name="Finance CFO"),
                        raw_item=SimpleNamespace(name="consult_expense_analyst"),
                    )
                ],
                context_wrapper=SimpleNamespace(
                    usage=SimpleNamespace(
                        requests=1,
                        input_tokens=90,
                        output_tokens=30,
                        total_tokens=120,
                    )
                ),
            )

    runtime = OpenAICFORuntime(
        runner=FakeRunner(),
        agent_factory=lambda tools: "fake-agent",
        tool_builder=lambda context: ["finance-tool"],
    )

    result = await runtime.run(CONTEXT)

    assert result["agent_used"] == "cfo"
    assert result["reply"].startswith("Your cash flow is healthy.")
    assert result["data"].audit.status == "verified"
    assert result["_run_observations"].tool_calls[0].name == "consult_expense_analyst"
    assert result["_run_observations"].tool_calls[0].latency_ms >= 0
    assert result["_run_observations"].usage.total_tokens == 120


@pytest.mark.asyncio
async def test_openai_runtime_adds_deterministic_audit_when_output_has_no_json(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeRunner:
        async def run(self, agent, user_input, max_turns, hooks):
            assert hooks is not None
            return SimpleNamespace(final_output="Your spending looks controlled.")

    runtime = OpenAICFORuntime(
        runner=FakeRunner(),
        agent_factory=lambda tools: "fake-agent",
        tool_builder=lambda context: ["finance-tool"],
    )

    result = await runtime.run(CONTEXT)

    assert result["reply"] == "Your spending looks controlled."
    assert result["data"].audit.status == "needs_review"
    assert result["data"].audit.confidence == 0.62


def test_openai_finance_tool_payloads_are_structured():
    payloads = build_openai_finance_tool_payloads(CONTEXT)

    assert payloads["finance_context"]["user_id"] == "demo"
    assert payloads["finance_context"]["runtime_policy"]["complexity"] == "moderate"
    assert payloads["expense_snapshot"]["expense_total"] == 1200
    assert payloads["anomaly_summary"]["anomaly_count"] == 1
    assert payloads["cashflow_summary"]["net_total"] == 3800
    assert payloads["expense_analyst_review"]["specialist"] == "expense_analyst"
    assert payloads["budget_coach_plan"]["specialist"] == "budget_coach"
    assert payloads["audit_review"]["specialist"] == "auditor"
    assert payloads["audit_review"]["audit"]["status"] == "needs_review"
