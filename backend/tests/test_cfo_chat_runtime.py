import logging

import pytest

from app.runtime.orchestration.factory import build_finance_runtime
from tests.cfo_decision_fakes import direct, execute


@pytest.mark.asyncio
async def test_runtime_uses_self_hosted_multi_agent_path(monkeypatch, caplog):
    from app.runtime.orchestration import finance_runtime

    saved_records = []
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )
    runtime = build_finance_runtime(decision_engine=execute("finance.expense_review"))
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
    assert trace["model_name"] is None
    assert trace["cost"]["status"] == "not_applicable"
    assert trace["cost"]["billing_totals"] == []
    assert trace["selected_agents"] == ["cfo", "expense_analyst", "auditor"]

    tool_calls = {call["name"]: call for call in trace["tool_calls"]}
    assert tool_calls["get_finance_context"]["status"] == "called"
    assert tool_calls["get_expense_snapshot"]["status"] == "called"
    assert tool_calls["get_anomaly_summary"]["status"] == "called"
    assert tool_calls["consult_expense_analyst"]["status"] == "called"
    assert tool_calls["consult_auditor"]["status"] == "called"

    assert [
        (h["from_agent"], h["to_agent"], h["status"], h["reason"])
        for h in trace["handoffs"]
    ] == [
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
async def test_runtime_binds_all_capabilities_before_execution(monkeypatch):
    from app.runtime.orchestration import finance_runtime

    saved_records = []
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )
    # The first planned capability is granted and the second is denied. The
    # first tool must still not run because binding is an all-or-nothing phase.
    runtime = build_finance_runtime(
        granted_capabilities={"finance.context"},
        decision_engine=execute("finance.expense_review"),
        llm_client=None,
    )

    result = await runtime.handle(
        user_id="demo",
        message="Please analyze my spending",
        profile={"name": "Demo"},
        transactions=[{"amount": -100, "category": "shopping"}],
        monthly_totals=[],
        chat_history=[],
    )

    assert result["execution"] == {
        "outcome": "blocked",
        "evidence_available": False,
        "specialist_findings_available": False,
        "process_available": False,
        "policy_blocked": True,
    }
    assert saved_records[0].policy["capability_rejection"]["status"] == "disallowed"
    assert not {
        "get_finance_context",
        "get_import_quality_report",
        "get_expense_snapshot",
        "consult_expense_analyst",
    }.intersection(call.name for call in saved_records[0].tool_calls)


@pytest.mark.asyncio
async def test_runtime_runs_sourced_read_only_investment_team(monkeypatch):
    from app.runtime.execution import finance_toolset
    from app.runtime.orchestration import finance_runtime

    saved_records = []

    class FakeResearchService:
        def get_instrument_research(self, *args, **kwargs):
            return object()

    monkeypatch.setattr(
        finance_toolset,
        "get_investment_research_service",
        lambda: FakeResearchService(),
    )
    monkeypatch.setattr(
        finance_toolset,
        "project_instrument_research",
        lambda snapshot: {
            "status": "available",
            "symbol": "AAPL",
            "asset_type": "equity",
            "profile": {
                "name": "Apple Inc.",
                "currency": "USD",
                "source": "openbb:yfinance",
            },
            "quote": {
                "price": {"amount": "210.50", "currency": "USD"},
                "quote_as_of": "2026-07-18T20:00:00Z",
                "source": "openbb:yfinance",
            },
            "history": {
                "date_from": "2026-04-20",
                "date_to": "2026-07-18",
                "bar_count": 62,
                "change_percent": "4.25",
                "source": "openbb:yfinance",
            },
            "evidence": [
                {
                    "kind": "quote",
                    "source": "openbb:yfinance",
                    "as_of": "2026-07-18T20:00:00Z",
                    "description": "End-of-day market quote",
                }
            ],
            "limitations": ["Quote is not an executable broker price."],
            "trade_actions_allowed": False,
        },
    )
    monkeypatch.setattr(
        finance_toolset, "list_latest_quality_reports_db", lambda user_id: []
    )
    monkeypatch.setattr(finance_runtime, "write_session_context", lambda **kwargs: None)
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )

    runtime = build_finance_runtime(
        decision_engine=execute("investment.research_review"),
        llm_client=None,
    )
    result = await runtime.handle(
        user_id="demo",
        message="请分析股票 AAPL",
        profile={"name": "Demo", "preferences": {"preferred_language": "zh"}},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    assert result["execution"]["outcome"] == "executed"
    assert [item["agent"] for item in result["data"]["findings"]] == [
        "investment_research",
        "investment_research",
    ]
    assert result["data"]["audit"]["status"] == "needs_review"
    assert [card["label"] for card in result["data"]["summary_cards"]] == [
        "最近行情",
        "观察期变化",
        "证据来源",
    ]
    assert "交易" in result["reply"]
    assert "买入" not in result["reply"] and "卖出" not in result["reply"]

    record = saved_records[0]
    assert record.selected_agents == ["cfo", "investment_research", "auditor"]
    assert [handoff.to_agent for handoff in record.handoffs] == [
        "investment_research",
        "auditor",
    ]
    tool_names = {call.name for call in record.tool_calls if call.status == "called"}
    assert "get_investment_research_context" in tool_names
    assert "consult_investment_research" in tool_names
    assert "consult_auditor" in tool_names


@pytest.mark.asyncio
async def test_runtime_degrades_without_fabricating_unavailable_market_data(
    monkeypatch,
):
    from app.runtime.execution import finance_toolset
    from app.runtime.orchestration import finance_runtime

    saved_records = []

    class UnavailableResearchService:
        def get_instrument_research(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        finance_toolset,
        "get_investment_research_service",
        lambda: UnavailableResearchService(),
    )
    monkeypatch.setattr(
        finance_toolset, "list_latest_quality_reports_db", lambda user_id: []
    )
    monkeypatch.setattr(finance_runtime, "write_session_context", lambda **kwargs: None)
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )

    runtime = build_finance_runtime(
        decision_engine=execute("investment.research_review"),
        llm_client=None,
    )
    result = await runtime.handle(
        user_id="demo",
        message="Analyze stock AAPL",
        profile={"name": "Demo"},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    assert result["data"]["summary_cards"] == []
    assert result["data"]["audit"]["status"] == "data_limited"
    assert result["execution"]["evidence_available"] is False
    assert "cannot complete" in result["reply"]
    assert "210.50" not in result["reply"]
    assert saved_records[0].selected_agents == [
        "cfo",
        "investment_research",
        "auditor",
    ]


@pytest.mark.asyncio
async def test_runtime_persists_output_validation_failure(monkeypatch, caplog):
    from app.runtime.orchestration import finance_runtime

    saved_records = []
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )
    runtime = build_finance_runtime(decision_engine=execute("finance.expense_review"))
    monkeypatch.setattr(
        runtime.response_builder,
        "build",
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
    runtime = build_finance_runtime(decision_engine=direct("好的，我们继续。"))
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
    assert result["execution"]["outcome"] == "direct_response"
    assert result["execution"]["process_available"] is False
    assert result["execution"]["evidence_available"] is False
    assert steps == []

    record = saved_records[0]
    assert record.selected_agents == ["cfo"]
    assert [call.name for call in record.tool_calls] == ["cfo_decide"]
    assert record.handoffs == []
    assert record.policy["turn_execution"]["outcome"] == "direct_response"
