from models.agent_data import (
    AgentAction,
    AgentAudit,
    AgentFinding,
    FinanceAgentData,
    SummaryCard,
    normalize_finance_agent_data,
)
from models.chat import ChatResponse


def test_finance_agent_data_accepts_expected_sections():
    data = FinanceAgentData(
        summary_cards=[
            SummaryCard(
                label="Budget risk",
                value="Low",
                status="good",
                note="Spending is below the monthly target.",
            )
        ],
        findings=[
            AgentFinding(
                agent="expense_analyst",
                title="Dining increased",
                evidence=["Dining spend is 18% above the prior average."],
            )
        ],
        actions=[
            AgentAction(
                title="Set a dining alert",
                rationale="The category is the main monthly variance.",
                effort="low",
                impact="medium",
            )
        ],
        audit=AgentAudit(
            confidence=0.82,
            status="verified",
            warnings=[],
        ),
    )

    dumped = data.model_dump()

    assert dumped["summary_cards"][0]["status"] == "good"
    assert dumped["findings"][0]["agent"] == "expense_analyst"
    assert dumped["actions"][0]["effort"] == "low"
    assert dumped["audit"]["confidence"] == 0.82


def test_normalize_finance_agent_data_discards_invalid_sections():
    normalized = normalize_finance_agent_data(
        {
            "summary_cards": [{"label": "Cash flow", "value": "+1200", "status": "good"}],
            "findings": [{"agent": "auditor", "title": "Data limited", "evidence": []}],
            "actions": [{"title": "Broken action", "rationale": "Missing effort and impact"}],
            "audit": {"confidence": 2.5, "status": "verified", "warnings": []},
        }
    )

    assert normalized is not None
    assert len(normalized.summary_cards or []) == 1
    assert len(normalized.findings or []) == 1
    assert normalized.actions is None
    assert normalized.audit is None


def test_normalize_finance_agent_data_returns_none_without_valid_sections():
    assert normalize_finance_agent_data({}) is None
    assert normalize_finance_agent_data(
        {
            "summary_cards": [{"label": "Missing value"}],
            "findings": [{"agent": "auditor"}],
            "actions": [{"title": "Broken action"}],
            "audit": {"confidence": 2.5, "status": "verified"},
        }
    ) is None
    assert normalize_finance_agent_data(FinanceAgentData()) is None


def test_chat_response_accepts_finance_agent_data():
    data = FinanceAgentData(
        audit=AgentAudit(
            confidence=0.5,
            status="data_limited",
            warnings=["Only 30 days of transactions were available."],
        )
    )

    response = ChatResponse(
        reply="本月现金流稳定，但数据样本有限。",
        agent_used="cfo",
        data=data,
    )

    assert response.data.audit.status == "data_limited"


def test_chat_response_discards_legacy_agent_data_sections():
    response = ChatResponse(
        reply="Legacy payload ignored.",
        data={"category_summary": {}, "anomalies": []},
    )

    assert response.data is None


def test_chat_response_discards_malformed_known_sections():
    response = ChatResponse(
        reply="Malformed payload ignored.",
        data={"actions": [{"title": "Broken", "rationale": "x"}]},
    )

    assert response.data is None


def test_chat_response_normalizes_valid_raw_agent_data():
    response = ChatResponse(
        reply="Valid payload accepted.",
        data={
            "summary_cards": [
                {
                    "label": "Cash flow",
                    "value": "+1200",
                    "status": "good",
                }
            ]
        },
    )

    assert isinstance(response.data, FinanceAgentData)
    assert response.data.summary_cards[0].label == "Cash flow"
