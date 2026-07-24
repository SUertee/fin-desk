import pytest

from app.agents.cfo.decision import CapabilityRequest, CfoTurnDecision
from app.evals.cfo_runtime_acceptance import (
    build_cfo_runtime_acceptance_report,
    evaluate_cfo_runtime_acceptance_case,
    load_cfo_runtime_acceptance_cases,
)
from app.runtime.orchestration.factory import build_finance_runtime
from tests.cfo_decision_fakes import StaticDecisionEngine


@pytest.mark.asyncio
async def test_cfo_runtime_acceptance_fixture_passes_offline(
    monkeypatch,
):
    from app.runtime.execution import finance_toolset
    from app.runtime.orchestration import finance_runtime

    saved_records = []
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )
    monkeypatch.setattr(
        finance_runtime,
        "write_session_context",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        finance_toolset,
        "list_latest_quality_reports_db",
        lambda user_id: [],
    )

    cases = load_cfo_runtime_acceptance_cases()
    results = []
    observations = {}
    for case in cases:
        saved_records.clear()
        decision = CfoTurnDecision(
            action=case.decision.action,
            reply=case.decision.reply,
            capability_requests=[
                CapabilityRequest(capability_id=capability_id)
                for capability_id in case.decision.capability_ids
            ],
        )
        runtime = build_finance_runtime(
            decision_engine=StaticDecisionEngine(decision),
            granted_capabilities=(
                set(case.granted_capabilities)
                if case.granted_capabilities is not None
                else None
            ),
            llm_client=None,
        )
        response = await runtime.handle(
            user_id=case.user_id,
            **case.input.model_dump(),
        )
        assert len(saved_records) == 1
        observations[case.case_id] = (response, saved_records[0])
        results.append(
            evaluate_cfo_runtime_acceptance_case(
                case,
                response,
                saved_records[0],
            )
        )

    report = build_cfo_runtime_acceptance_report(results)

    assert len(cases) == 20
    assert report.passed == report.total == 20, [
        (item.case_id, item.failures) for item in report.failures()
    ]
    assert set(report.by_category) == {
        "conversation",
        "clarification",
        "finance_execution",
        "specialist",
        "policy",
    }
    assert all(score.accuracy == 1.0 for score in report.by_category.values())

    grounded_case = next(
        case
        for case in cases
        if case.case_id == "finance_context_with_transactions"
    )
    grounded_response, grounded_record = observations[grounded_case.case_id]
    fabricated_response = {
        **grounded_response,
        "reply": f"{grounded_response['reply']} 999999",
    }
    fabricated_result = evaluate_cfo_runtime_acceptance_case(
        grounded_case,
        fabricated_response,
        grounded_record,
    )
    assert "reply has unsupported numbers" in fabricated_result.failures[-1]


def test_cfo_runtime_acceptance_reports_mismatched_execution_fact():
    case = load_cfo_runtime_acceptance_cases()[0]
    response = {
        "reply": "你好，我是你的 CFO。",
        "agent_used": "cfo",
        "request_id": "acceptance-failure",
        "data": None,
        "execution": {
            "outcome": "direct_response",
            "evidence_available": True,
            "specialist_findings_available": False,
            "process_available": False,
            "policy_blocked": False,
        },
    }
    record = {
        "request_id": "acceptance-failure",
        "entrypoint": "chat",
        "user_id": case.user_id,
        "runtime_requested": "self_hosted",
        "runtime_used": "self_hosted",
        "selected_agents": ["cfo"],
        "output_validations": [
            {
                "agent": "cfo",
                "contract": "ChatResponse",
                "status": "passed",
            }
        ],
        "output_contract": "ChatResponse",
        "policy": {"turn_execution": response["execution"]},
        "latency_ms": 1,
    }

    result = evaluate_cfo_runtime_acceptance_case(case, response, record)

    assert result.passed is False
    assert result.failures == [
        "execution.evidence_available=True, expected False"
    ]
