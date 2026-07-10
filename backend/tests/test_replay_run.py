import json
from pathlib import Path

from app.evals import replay_run
from app.models.runtime import AgentOutputValidation, AgentRunRecord, AgentToolCall


def _record() -> dict:
    return AgentRunRecord(
        request_id="req-pass",
        entrypoint="chat",
        user_id="eval-spending",
        runtime_requested="openai",
        runtime_used="openai",
        selected_agents=["cfo", "expense_analyst", "auditor"],
        tool_calls=[
            AgentToolCall(name="get_finance_context", status="called"),
            AgentToolCall(name="get_expense_snapshot", status="called"),
            AgentToolCall(name="get_anomaly_summary", status="called"),
            AgentToolCall(name="consult_expense_analyst", status="called"),
            AgentToolCall(name="consult_auditor", status="called"),
        ],
        output_validations=[
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
            )
        ],
        output_contract="ChatResponse",
        audit_status="needs_review",
        latency_ms=12.0,
    ).model_dump(mode="json")


def test_replay_agent_run_evaluates_persisted_record():
    report = replay_run.replay_agent_run(
        "req-pass",
        case_id="chat_spending_review",
        record_loader=lambda request_id: _record(),
    )

    assert report.record_found is True
    assert report.evaluation is not None
    assert report.evaluation.passed is True
    assert report.record_summary["selected_agents"] == [
        "cfo",
        "expense_analyst",
        "auditor",
    ]


def test_replay_agent_run_reports_missing_record():
    report = replay_run.replay_agent_run(
        "missing",
        case_id="chat_spending_review",
        record_loader=lambda request_id: None,
    )

    assert report.record_found is False
    assert report.error == "Agent run record not found"


def test_replay_agent_run_reports_missing_case():
    report = replay_run.replay_agent_run(
        "req-pass",
        case_id="does_not_exist",
        record_loader=lambda request_id: _record(),
    )

    assert report.record_found is True
    assert report.error == "Eval case not found: does_not_exist"


def test_replay_cli_returns_nonzero_for_failed_eval(monkeypatch, tmp_path, capsys):
    fixture = {
        "case_id": "requires_budget",
        "entrypoint": "chat",
        "user_id": "eval-spending",
        "input": {},
        "expected": {"selected_agents": ["budget_coach"]},
    }
    fixture_path = Path(tmp_path) / "requires_budget.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    monkeypatch.setattr(
        replay_run,
        "get_agent_run_record_db",
        lambda request_id: _record(),
    )

    exit_code = replay_run.main(
        ["req-pass", "--case-id", "requires_budget", "--fixtures-dir", str(tmp_path)]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "missing selected agent: budget_coach" in captured.out
