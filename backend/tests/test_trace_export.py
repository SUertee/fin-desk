import json

from app.evals import trace_export
from app.models.runtime import AgentOutputValidation, AgentRunRecord, AgentToolCall


def _spending_record(
    *,
    request_id: str = "req-spending",
    user_id: str = "eval-spending",
    selected_agents: list[str] | None = None,
    tool_calls: list[AgentToolCall] | None = None,
    output_validations: list[AgentOutputValidation] | None = None,
) -> AgentRunRecord:
    return AgentRunRecord(
        request_id=request_id,
        entrypoint="chat",
        user_id=user_id,
        runtime_requested="openai",
        runtime_used="openai",
        selected_agents=selected_agents
        or ["cfo", "expense_analyst", "auditor"],
        tool_calls=tool_calls
        or [
            AgentToolCall(name="get_finance_context", status="called"),
            AgentToolCall(name="get_expense_snapshot", status="called"),
            AgentToolCall(name="get_anomaly_summary", status="called"),
            AgentToolCall(name="consult_expense_analyst", status="called"),
            AgentToolCall(name="consult_auditor", status="called"),
        ],
        output_validations=output_validations
        or [
            AgentOutputValidation(
                agent="expense_analyst",
                contract="SpecialistAgentOutput",
                status="passed",
            ),
            AgentOutputValidation(
                agent="auditor",
                contract="SpecialistAgentOutput",
                status="passed",
            ),
            AgentOutputValidation(
                agent="cfo",
                contract="ChatResponse",
                status="passed",
            ),
        ],
        output_contract="ChatResponse",
        audit_status="needs_review",
        latency_ms=12.0,
    )


def test_trace_export_jsonl_roundtrip_and_report_passes(tmp_path):
    export_path = tmp_path / "traces.jsonl"
    item = trace_export.build_trace_export_item(
        _spending_record(),
        case_id="chat_spending_review",
    )

    trace_export.write_trace_export_items([item], export_path)

    loaded_items = trace_export.load_trace_export_items(export_path)
    report = trace_export.evaluate_trace_export_file(export_path)

    assert loaded_items[0].case_id == "chat_spending_review"
    assert report.summary.ok is True
    assert report.summary.total_records == 1
    assert report.summary.passed_records == 1
    assert report.results[0].case_id == "chat_spending_review"
    assert report.results[0].tool_calls[0]["name"] == "get_finance_context"


def test_trace_export_json_envelope_infers_case_by_entrypoint_and_user(tmp_path):
    export_path = tmp_path / "traces.json"
    trace_export.write_trace_export_items(
        [_spending_record(request_id="req-inferred")],
        export_path,
        jsonl=False,
    )

    report = trace_export.evaluate_trace_export_file(export_path)

    assert report.summary.ok is True
    assert report.results[0].case_id == "chat_spending_review"
    assert report.results[0].request_id == "req-inferred"


def test_trace_export_cli_returns_nonzero_for_failed_eval(tmp_path, capsys):
    export_path = tmp_path / "failed.jsonl"
    record = _spending_record(
        selected_agents=["cfo"],
        tool_calls=[AgentToolCall(name="get_finance_context", status="called")],
        output_validations=[],
    )
    trace_export.write_trace_export_items(
        [trace_export.build_trace_export_item(record, case_id="chat_spending_review")],
        export_path,
    )

    exit_code = trace_export.main([str(export_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "missing selected agent: expense_analyst" in captured.out
    assert "missing required tool call: consult_auditor" in captured.out


def test_trace_export_cli_writes_report_and_allows_skipped_records(tmp_path):
    export_path = tmp_path / "unmatched.json"
    report_path = tmp_path / "reports" / "trace-report.json"
    raw_record = _spending_record(
        request_id="req-unmatched",
        user_id="unknown-user",
    ).model_dump(mode="json")
    export_path.write_text(json.dumps(raw_record), encoding="utf-8")

    exit_code = trace_export.main(
        [str(export_path), "--allow-skipped", "--output", str(report_path)]
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["summary"]["ok"] is True
    assert report["summary"]["skipped_records"] == 1
    assert "No eval case matched" in report["results"][0]["skipped_reason"]
