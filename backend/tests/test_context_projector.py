import pytest

from app.runtime.execution.artifact_registry import ArtifactRegistry
from app.runtime.execution.context_projector import ContextProjector


def _artifacts(**values) -> ArtifactRegistry:
    registry = ArtifactRegistry()
    for name, value in values.items():
        registry.put(name, value)
    return registry


FULL_CONTEXT = {
    "reply_language": "zh",
    "profile": {"name": "Private User"},
    "chat_history": [{"role": "user", "content": "private history"}],
    "memory_context": {"summary": "private memory"},
    "transactions_sample": [{"description": "raw transaction", "amount": -10}],
    "expense_snapshot": {"transaction_count": 1},
    "budget_snapshot": {"status": "watch"},
    "import_quality": {"reports": [{"source_type": "bank"}]},
    "investment_research": {"status": "available", "symbol": "AAPL"},
}


def test_expense_projection_exposes_only_registered_evidence():
    projected = ContextProjector().project(
        "expense_analyst",
        finance_context=FULL_CONTEXT,
        artifacts=_artifacts(
            get_finance_context={"loaded": True},
            get_expense_snapshot={"transaction_count": 1},
            get_import_quality_report={"reports": []},
            get_budget_snapshot={"status": "watch"},
        ),
    )

    assert projected.evidence == {
        "reply_language": "zh",
        "expense_snapshot": {"transaction_count": 1},
        "import_quality": {"reports": [{"source_type": "bank"}]},
    }
    assert projected.artifact_refs == (
        "artifact://get_expense_snapshot",
        "artifact://get_import_quality_report",
    )


def test_budget_projection_cannot_read_expense_or_private_context():
    projected = ContextProjector().project(
        "budget_coach",
        finance_context=FULL_CONTEXT,
        artifacts=_artifacts(
            get_finance_context={"loaded": True},
            get_budget_snapshot={"status": "watch"},
            get_expense_snapshot={"transaction_count": 1},
        ),
    )

    assert projected.evidence == {
        "reply_language": "zh",
        "budget_snapshot": {"status": "watch"},
    }
    assert projected.artifact_refs == ("artifact://get_budget_snapshot",)


def test_missing_artifact_omits_field_and_provenance():
    projected = ContextProjector().project(
        "expense_analyst",
        finance_context=FULL_CONTEXT,
        artifacts=_artifacts(get_expense_snapshot={"transaction_count": 1}),
    )

    assert "import_quality" not in projected.evidence
    assert projected.artifact_refs == ("artifact://get_expense_snapshot",)


def test_auditor_receives_presence_signal_not_raw_transactions():
    projected = ContextProjector().project(
        "auditor",
        finance_context=FULL_CONTEXT,
        artifacts=_artifacts(
            get_finance_context={"loaded": True},
            get_investment_research_context={"status": "available"},
        ),
    )

    assert projected.evidence == {
        "reply_language": "zh",
        "transaction_evidence_available": True,
        "investment_research": {
            "status": "available",
            "symbol": "AAPL",
        },
    }
    assert projected.artifact_refs == (
        "artifact://get_finance_context",
        "artifact://get_investment_research_context",
    )


def test_unknown_specialist_has_no_implicit_full_context_fallback():
    with pytest.raises(ValueError, match="No context projection registered"):
        ContextProjector().project(
            "unknown",
            finance_context=FULL_CONTEXT,
            artifacts=ArtifactRegistry(),
        )
