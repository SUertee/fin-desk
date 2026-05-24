import pytest

from agents.deep_runtime import FinanceTeamRuntime


class FakeLangGraphRunner:
    async def ainvoke(self, state):
        return {
            "final_reply": "fallback reply",
            "agent_used": "general",
            "agent_data": {
                "audit": {
                    "confidence": 0.4,
                    "status": "data_limited",
                    "warnings": ["fallback used"],
                }
            },
        }


@pytest.mark.asyncio
async def test_runtime_uses_langgraph_when_flag_is_langgraph(monkeypatch):
    monkeypatch.setenv("FINANCE_AGENT_RUNTIME", "langgraph")
    runtime = FinanceTeamRuntime(langgraph_runner=FakeLangGraphRunner())

    result = await runtime.handle(
        user_id="demo",
        message="hello",
        profile={"name": "Demo"},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    assert result["reply"] == "fallback reply"
    assert result["agent_used"] == "general"
    assert result["data"].audit.status == "data_limited"


@pytest.mark.asyncio
async def test_runtime_falls_back_when_deepagents_fails(monkeypatch):
    monkeypatch.setenv("FINANCE_AGENT_RUNTIME", "deepagents")

    class FailingRuntime(FinanceTeamRuntime):
        async def _invoke_deepagents(self, context):
            raise RuntimeError("deepagents unavailable")

    runtime = FailingRuntime(langgraph_runner=FakeLangGraphRunner())

    result = await runtime.handle(
        user_id="demo",
        message="hello",
        profile={"name": "Demo"},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    assert result["reply"] == "fallback reply"
    assert result["agent_used"] == "general"
    assert result["data"].audit.warnings == ["fallback used"]
