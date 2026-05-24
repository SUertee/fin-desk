import logging
from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_orchestrator_saves_and_logs_error_reply(monkeypatch, caplog):
    from agents import orchestrator

    class FailingRuntime:
        async def handle(self, **kwargs):
            raise RuntimeError("runtime unavailable")

    saved_messages = []

    monkeypatch.setattr(orchestrator, "_runtime", FailingRuntime())
    monkeypatch.setattr(
        orchestrator,
        "get_profile",
        lambda user_id: SimpleNamespace(model_dump=lambda: {"name": "Demo"}),
    )
    monkeypatch.setattr(orchestrator, "get_chat_history", lambda user_id: [])
    monkeypatch.setattr(
        orchestrator,
        "save_message",
        lambda user_id, role, content: saved_messages.append((user_id, role, content)),
    )
    caplog.set_level(logging.INFO, logger=orchestrator.logger.name)

    result = await orchestrator.handle_message(user_id="demo", message="hello")

    assert result == {
        "reply": "Sorry, something went wrong. Please try again.",
        "agent_used": "error",
        "data": None,
    }
    assert saved_messages == [
        ("demo", "user", "hello"),
        ("demo", "assistant", "Sorry, something went wrong. Please try again."),
    ]
    assert "Handled message for user=demo, agent=error" in caplog.text
