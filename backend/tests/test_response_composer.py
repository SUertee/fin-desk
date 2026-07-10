from app.models.agent_data import AgentAction, AgentAudit, AgentFinding, SummaryCard
from app.runtime.response.response_composer import (
    compose_finance_chat_response,
    compose_runtime_response,
)


def test_compose_runtime_response_normalizes_agent_result():
    response = compose_runtime_response(
        {
            "final_reply": "final answer",
            "agent_used": "expense_analyst",
            "agent_data": {
                "audit": {
                    "confidence": 0.7,
                    "status": "verified",
                    "warnings": [],
                }
            },
        }
    )

    assert response["reply"] == "final answer"
    assert response["agent_used"] == "expense_analyst"
    assert response["data"].audit.status == "verified"


def test_compose_runtime_response_uses_default_agent_and_discards_bad_data():
    response = compose_runtime_response(
        {
            "agent_reply": "plain text",
            "agent_data": {"actions": [{"title": "Broken"}]},
        },
        default_agent="general",
    )

    assert response == {
        "reply": "plain text",
        "agent_used": "general",
        "data": None,
    }


def test_compose_runtime_response_adds_audit_repair_when_data_missing():
    response = compose_runtime_response(
        {"reply": "plain answer", "agent_used": "cfo"},
        audit_repair={
            "audit": {
                "confidence": 0.42,
                "status": "data_limited",
                "warnings": ["No active transactions were available for evidence."],
            }
        },
    )

    assert response["data"].audit.status == "data_limited"
    assert response["data"].audit.confidence == 0.42


def test_compose_runtime_response_preserves_valid_agent_audit():
    response = compose_runtime_response(
        {
            "reply": "audited answer",
            "data": {
                "audit": {
                    "confidence": 0.9,
                    "status": "verified",
                    "warnings": [],
                }
            },
        },
        audit_repair={
            "audit": {
                "confidence": 0.3,
                "status": "data_limited",
                "warnings": ["repair warning"],
            }
        },
    )

    assert response["data"].audit.status == "verified"
    assert response["data"].audit.confidence == 0.9


def test_compose_runtime_response_repairs_malformed_audit_with_audit_repair():
    response = compose_runtime_response(
        {
            "reply": "malformed audit answer",
            "data": {"audit": {"confidence": 2.5, "status": "verified"}},
        },
        audit_repair={
            "audit": {
                "confidence": 0.62,
                "status": "needs_review",
                "warnings": ["Audit repair used."],
            }
        },
    )

    assert response["data"].audit.status == "needs_review"
    assert response["data"].audit.warnings == ["Audit repair used."]


def test_compose_finance_chat_response_builds_stable_payload():
    response = compose_finance_chat_response(
        reply="CFO response",
        summary_cards=[SummaryCard(label="Cash flow", value="+1200", status="good")],
        findings=[
            AgentFinding(
                agent="expense_analyst",
                title="Dining is elevated",
                evidence=["Dining totals 320."],
            )
        ],
        actions=[
            AgentAction(
                title="Set dining cap",
                rationale="Dining is the largest flexible category.",
                effort="low",
                impact="medium",
            )
        ],
        audit=AgentAudit(confidence=0.8, status="verified", warnings=[]),
    )

    assert response["agent_used"] == "cfo"
    assert response["data"]["summary_cards"][0]["label"] == "Cash flow"
    assert response["data"]["findings"][0]["agent"] == "expense_analyst"
