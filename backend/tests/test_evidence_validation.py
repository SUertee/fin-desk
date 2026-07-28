from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistFinding,
)
from app.runtime.execution.artifact_registry import ArtifactRegistry
from app.runtime.execution.evidence_validation import (
    EvidenceJoiner,
    EvidenceValidator,
    SpecialistArtifact,
)


def _output(
    specialist: str = "expense_analyst",
    *,
    finding: SpecialistFinding | None = None,
) -> SpecialistAgentOutput:
    return SpecialistAgentOutput(
        specialist=specialist,
        confidence=0.9,
        findings=[finding] if finding is not None else [],
    )


def test_joiner_keeps_current_run_artifacts_and_specialist_provenance():
    registry = ArtifactRegistry()
    registry.put("get_expense_snapshot", {"expense_total": 120})
    specialist = SpecialistArtifact(
        specialist="expense_analyst",
        output=_output(
            finding=SpecialistFinding(
                title="Dining increased",
                evidence=["Dining was 24% of expenses."],
            )
        ),
        artifact_refs=("artifact://get_expense_snapshot",),
    )

    bundle = EvidenceJoiner().join(registry, [specialist])
    result = EvidenceValidator().validate(bundle)

    assert bundle.tool_artifacts == {
        "get_expense_snapshot": {"expense_total": 120}
    }
    assert result.status == "validated"
    assert result.accepted_specialists == ("expense_analyst",)
    assert bundle.outputs_for(result.accepted_specialists) == {
        "expense_analyst": specialist.output
    }


def test_validator_rejects_missing_current_run_artifact_reference():
    bundle = EvidenceJoiner().join(
        ArtifactRegistry(),
        [
            SpecialistArtifact(
                specialist="expense_analyst",
                output=_output(),
                artifact_refs=("artifact://get_expense_snapshot",),
            )
        ],
    )

    result = EvidenceValidator().validate(bundle)

    assert result.status == "rejected"
    assert result.rejected_specialists == ("expense_analyst",)
    assert result.reason_codes == (
        "missing_artifact_ref:expense_analyst:get_expense_snapshot",
    )


def test_validator_rejects_findings_without_evidence_or_complete_source():
    registry = ArtifactRegistry()
    registry.put("search_web_research", {"items": []})
    bundle = EvidenceJoiner().join(
        registry,
        [
            SpecialistArtifact(
                specialist="market_context",
                output=_output(
                    "market_context",
                    finding=SpecialistFinding(
                        title="Rates changed",
                        evidence=[],
                        source_url="https://example.com/rates",
                    ),
                ),
                artifact_refs=("artifact://search_web_research",),
            )
        ],
    )

    result = EvidenceValidator().validate(bundle)

    assert result.status == "limited"
    assert result.rejected_specialists == ("market_context",)
    assert result.reason_codes == (
        "finding_without_evidence:market_context:0",
        "incomplete_external_source:market_context:0",
    )


def test_validator_isolates_invalid_specialist_and_bounds_ledger_projection():
    registry = ArtifactRegistry()
    registry.put("get_expense_snapshot", {"private_rows": [1, 2, 3]})
    registry.put("get_budget_snapshot", {"monthly_income": 5000})
    bundle = EvidenceJoiner().join(
        registry,
        [
            SpecialistArtifact(
                specialist="expense_analyst",
                output=_output(
                    finding=SpecialistFinding(
                        title="Unsupported finding",
                        evidence=[""],
                    )
                ),
                artifact_refs=("artifact://get_expense_snapshot",),
            ),
            SpecialistArtifact(
                specialist="budget_coach",
                output=_output(
                    "budget_coach",
                    finding=SpecialistFinding(
                        title="Budget is usable",
                        evidence=["Monthly income is configured."],
                    ),
                ),
                artifact_refs=("artifact://get_budget_snapshot",),
            ),
        ],
    )

    result = EvidenceValidator().validate(bundle)
    projection = result.ledger_dump()

    assert result.status == "limited"
    assert result.accepted_specialists == ("budget_coach",)
    assert result.rejected_specialists == ("expense_analyst",)
    assert set(bundle.outputs_for(result.accepted_specialists)) == {
        "budget_coach"
    }
    assert set(projection) == {
        "stage",
        "status",
        "accepted_specialists",
        "rejected_specialists",
        "reason_codes",
    }
    assert "private_rows" not in str(projection)
