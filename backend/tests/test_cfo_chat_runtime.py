import logging
from types import SimpleNamespace

import pytest

from app.runtime.cfo_chat_runtime import FinanceTeamRuntime


class FakeOpenAIRuntime:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "reply": "openai cfo reply",
            "agent_used": "cfo",
            "data": None,
        }
        self.error = error
        self.context = None

    async def run(self, context):
        self.context = context
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_runtime_uses_openai_only_path(caplog):
    fake_openai = FakeOpenAIRuntime()
    runtime = FinanceTeamRuntime(openai_runtime=fake_openai)
    caplog.set_level(logging.INFO, logger="app.runtime.cfo_chat_runtime")

    result = await runtime.handle(
        user_id="demo",
        message="Please analyze my spending",
        profile={"name": "Demo"},
        transactions=[{"amount": -100, "category": "Dining"}],
        monthly_totals=[],
        chat_history=[],
    )

    assert result["reply"] == "openai cfo reply"
    assert result["agent_used"] == "cfo"
    assert fake_openai.context["runtime_policy"]["complexity"] == "moderate"
    assert fake_openai.context["expense_snapshot"]["expense_total"] == 100

    traces = [record.trace for record in caplog.records if hasattr(record, "trace")]
    assert traces[-1]["runtime_requested"] == "openai"
    assert traces[-1]["runtime_used"] == "openai"
    assert traces[-1]["tools_available"] == [
        "get_finance_context",
        "get_expense_snapshot",
        "get_budget_snapshot",
        "get_anomaly_summary",
        "get_cashflow_summary",
        "analyze_expense_patterns",
        "generate_budget_plan",
        "run_audit_review",
    ]


@pytest.mark.asyncio
async def test_runtime_raises_openai_errors(caplog):
    runtime = FinanceTeamRuntime(
        openai_runtime=FakeOpenAIRuntime(error=RuntimeError("openai unavailable"))
    )
    caplog.set_level(logging.INFO, logger="app.runtime.cfo_chat_runtime")

    with pytest.raises(RuntimeError, match="openai unavailable"):
        await runtime.handle(
            user_id="demo",
            message="hello",
            profile={"name": "Demo"},
            transactions=[],
            monthly_totals=[],
            chat_history=[],
        )

    traces = [record.trace for record in caplog.records if hasattr(record, "trace")]
    assert traces[-1]["runtime_requested"] == "openai"
    assert traces[-1]["runtime_used"] is None
    assert traces[-1]["error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_orchestrator_saves_and_logs_error_reply(monkeypatch, caplog):
    from app.agents import orchestrator

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
