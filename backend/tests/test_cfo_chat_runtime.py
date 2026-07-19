import logging
from types import SimpleNamespace

import pytest

from app.runtime.orchestration.finance_runtime import FinanceRuntime


@pytest.mark.asyncio
async def test_runtime_uses_self_hosted_multi_agent_path(monkeypatch, caplog):
    from app.runtime.orchestration import finance_runtime

    saved_records = []
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )
    runtime = FinanceRuntime()
    caplog.set_level(logging.INFO, logger="app.runtime.orchestration.finance_runtime")

    result = await runtime.handle(
        user_id="demo",
        message="Please analyze my spending and unusual expenses",
        profile={"name": "Demo", "monthly_income": 5000},
        transactions=[{"amount": -100, "category": "Dining"}],
        monthly_totals=[{"month": "2026-06", "net": 4200}],
        chat_history=[],
    )

    assert result["agent_used"] == "cfo"
    assert result["data"]["audit"]["status"] == "needs_review"
    assert result["data"]["findings"][0]["agent"] == "expense_analyst"

    traces = [record.trace for record in caplog.records if hasattr(record, "trace")]
    trace = traces[-1]
    assert trace["runtime_requested"] == "self_hosted"
    assert trace["runtime_used"] == "self_hosted"
    assert trace["model_name"] == "self-hosted-deterministic"
    assert trace["cost"]["status"] == "not_applicable"
    assert trace["cost"]["billing_totals"] == []
    assert trace["selected_agents"] == ["cfo", "expense_analyst", "auditor"]

    tool_calls = {call["name"]: call for call in trace["tool_calls"]}
    assert tool_calls["get_finance_context"]["status"] == "called"
    assert tool_calls["get_expense_snapshot"]["status"] == "called"
    assert tool_calls["get_anomaly_summary"]["status"] == "called"
    assert tool_calls["consult_expense_analyst"]["status"] == "called"
    assert tool_calls["consult_auditor"]["status"] == "called"

    assert [(h["from_agent"], h["to_agent"], h["status"], h["reason"]) for h in trace["handoffs"]] == [
        ("cfo", "expense_analyst", "completed", "typed_internal_handoff"),
        ("cfo", "auditor", "completed", "typed_internal_handoff"),
    ]
    # Bounded specialist output persists for evidence projection
    expense_handoff = trace["handoffs"][0]
    assert expense_handoff["output"]["specialist"] == "expense_analyst"
    assert expense_handoff["output"]["findings"]
    assert trace["output_validations"] == [
        {
            "agent": "expense_analyst",
            "contract": "SpecialistAgentOutput",
            "status": "passed",
            "errors": [],
        },
        {
            "agent": "auditor",
            "contract": "SpecialistAgentOutput",
            "status": "passed",
            "errors": [],
        },
        {
            "agent": "cfo",
            "contract": "ChatResponse",
            "status": "passed",
            "errors": [],
        },
    ]
    assert saved_records[0].request_id == trace["request_id"]
    assert saved_records[0].entrypoint == "chat"
    assert saved_records[0].runtime_used == "self_hosted"
    assert saved_records[0].selected_agents == ["cfo", "expense_analyst", "auditor"]


@pytest.mark.asyncio
async def test_runtime_persists_output_validation_failure(monkeypatch, caplog):
    from app.runtime.orchestration import finance_runtime

    saved_records = []
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )
    runtime = FinanceRuntime()
    monkeypatch.setattr(
        runtime,
        "_compose_response",
        lambda **kwargs: {"agent_used": "cfo", "data": None},
    )
    caplog.set_level(logging.INFO, logger="app.runtime.orchestration.finance_runtime")

    with pytest.raises(ValueError, match="invalid ChatResponse"):
        await runtime.handle(
            user_id="demo",
            message="Please analyze my spending",
            profile={"name": "Demo"},
            transactions=[],
            monthly_totals=[],
            chat_history=[],
        )

    assert saved_records[0].runtime_used is None
    assert saved_records[0].error_type == "ValueError"
    assert saved_records[0].output_validations[-1].status == "failed"
    assert saved_records[0].output_validations[-1].contract == "ChatResponse"
    assert "reply:" in saved_records[0].output_validations[-1].errors[0]


@pytest.mark.asyncio
async def test_runtime_short_circuits_acknowledgement_without_pipeline(monkeypatch):
    from app.runtime.orchestration import finance_runtime

    saved_records = []
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )
    runtime = FinanceRuntime()
    steps = []

    async def on_steps(payload):
        steps.append(payload)

    result = await runtime.handle(
        user_id="demo",
        message="哈哈",
        profile={"name": "Demo", "preferences": {"preferred_language": "zh"}},
        transactions=[{"amount": -100, "category": "shopping"}],
        monthly_totals=[{"month": "2026-06", "net": -100}],
        chat_history=[{"role": "assistant", "content": "上一轮 CFO 分析"}],
        on_pipeline_complete=on_steps,
    )

    assert result["agent_used"] == "cfo"
    assert result["data"] is None
    assert result["route"]["execution_path"] == "light_reply"
    assert result["route"]["emit_steps"] is False
    assert result["route"]["attach_evidence"] is False
    assert steps == []

    record = saved_records[0]
    assert record.selected_agents == ["cfo"]
    assert record.tool_calls == []
    assert record.handoffs == []
    assert record.policy["conversation_route"]["execution_path"] == "light_reply"


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
