"""Hermetic outcome grading for financially grounded CFO responses."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.specialists.contracts import SpecialistAgentOutput, SpecialistName
from app.evals.grounding_checks import (
    ISO_DATE_RE,
    collect_iso_dates,
    collect_supported_numbers,
    extract_number_tokens,
    normalize_number,
)
from app.knowledge import KnowledgeEvidenceArtifact
from app.runtime.execution.artifact_registry import ArtifactRegistry
from app.runtime.execution.evidence_validation import (
    EvidenceJoiner,
    EvidenceValidator,
    SpecialistArtifact,
)


GROUNDING_FIXTURES = (
    Path(__file__).with_name("fixtures") / "financial_grounding" / "cases.json"
)
GroundingCategory = Literal[
    "numeric_claim",
    "date_claim",
    "specialist_evidence",
    "knowledge_citation",
    "no_match",
    "conversation",
]

_HONEST_NO_MATCH_MARKERS = (
    "证据不足",
    "无法确定",
    "没有直接匹配",
    "未找到直接匹配",
    "insufficient evidence",
    "cannot determine",
    "no direct match",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpecialistEvidenceFixture(_StrictModel):
    specialist: SpecialistName
    artifact_refs: tuple[str, ...] = ()
    output: SpecialistAgentOutput


class FinancialGroundingCase(_StrictModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    category: GroundingCategory
    reply: str = Field(min_length=1, max_length=4000)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    specialist_artifacts: tuple[SpecialistEvidenceFixture, ...] = ()
    knowledge_artifacts: tuple[KnowledgeEvidenceArtifact, ...] = ()
    citation_ids: tuple[str, ...] = ()
    evidence_required: bool = False
    no_match_expected: bool = False


class FinancialGroundingResult(_StrictModel):
    case_id: str
    category: GroundingCategory
    passed: bool
    failures: list[str] = Field(default_factory=list, max_length=16)


class FinancialGroundingReport(_StrictModel):
    total: int
    passed: int
    results: list[FinancialGroundingResult]


def load_financial_grounding_cases(
    path: Path = GROUNDING_FIXTURES,
) -> list[FinancialGroundingCase]:
    payload = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    return [FinancialGroundingCase.model_validate(item) for item in payload["cases"]]


def evaluate_financial_grounding_case(
    case: FinancialGroundingCase,
) -> FinancialGroundingResult:
    failures: list[str] = []
    referenced_values: list[Any] = []

    values, unresolved = _resolve_artifact_refs(case.artifacts, case.evidence_refs)
    referenced_values.extend(values)
    if unresolved:
        failures.append("unresolved_artifact_ref")

    if case.specialist_artifacts:
        specialist_values, specialist_failures = _validate_specialist_evidence(case)
        referenced_values.extend(specialist_values)
        failures.extend(specialist_failures)

    cited_knowledge, citation_invalid = _resolve_knowledge_citations(case)
    referenced_values.extend(
        artifact.model_dump(mode="json") for artifact in cited_knowledge
    )
    if citation_invalid:
        failures.append("invalid_knowledge_citation")

    has_evidence_surface = bool(
        case.evidence_refs or case.specialist_artifacts or case.citation_ids
    )
    if case.category == "conversation" and has_evidence_surface:
        failures.append("unexpected_evidence_surface")

    if case.category != "conversation":
        supported_numbers = collect_supported_numbers(referenced_values)
        unsupported_numbers = {
            token
            for token in extract_number_tokens(case.reply, exclude_iso_dates=True)
            if normalize_number(token) not in supported_numbers
        }
        if unsupported_numbers:
            failures.append("unsupported_numeric_claim")

        supported_dates = collect_iso_dates(referenced_values)
        if any(date not in supported_dates for date in ISO_DATE_RE.findall(case.reply)):
            failures.append("unsupported_date_claim")

        if (
            case.evidence_required
            and not has_evidence_surface
            and not unsupported_numbers
            and not ISO_DATE_RE.search(case.reply)
        ):
            failures.append("missing_required_evidence")

    if case.no_match_expected:
        reply_lower = case.reply.lower()
        honest = any(marker in reply_lower for marker in _HONEST_NO_MATCH_MARKERS)
        if has_evidence_surface or not honest:
            failures.append("dishonest_no_match")

    unique_failures = list(dict.fromkeys(failures))
    return FinancialGroundingResult(
        case_id=case.case_id,
        category=case.category,
        passed=not unique_failures,
        failures=unique_failures,
    )


def run_financial_grounding_eval(
    cases: list[FinancialGroundingCase] | None = None,
) -> FinancialGroundingReport:
    selected_cases = cases or load_financial_grounding_cases()
    results = [evaluate_financial_grounding_case(case) for case in selected_cases]
    return FinancialGroundingReport(
        total=len(results),
        passed=sum(result.passed for result in results),
        results=results,
    )


def _resolve_artifact_refs(
    artifacts: dict[str, Any],
    refs: tuple[str, ...],
) -> tuple[list[Any], list[str]]:
    values: list[Any] = []
    unresolved: list[str] = []
    for ref in refs:
        if not ref.startswith("artifact://"):
            unresolved.append(ref)
            continue
        artifact_name = ref.removeprefix("artifact://")
        if not artifact_name or artifact_name not in artifacts:
            unresolved.append(ref)
            continue
        values.append(artifacts[artifact_name])
    return values, unresolved


def _validate_specialist_evidence(
    case: FinancialGroundingCase,
) -> tuple[list[Any], list[str]]:
    registry = ArtifactRegistry()
    for name, value in case.artifacts.items():
        registry.put(name, value)

    specialist_artifacts: list[SpecialistArtifact] = []
    referenced_values: list[Any] = []
    failures: list[str] = []
    for fixture in case.specialist_artifacts:
        values, unresolved = _resolve_artifact_refs(
            case.artifacts,
            fixture.artifact_refs,
        )
        referenced_values.extend(values)
        if unresolved:
            failures.append("unresolved_artifact_ref")
        if fixture.output.specialist != fixture.specialist:
            failures.append("specialist_evidence_rejected")
        specialist_artifacts.append(
            SpecialistArtifact(
                specialist=fixture.specialist,
                output=fixture.output,
                artifact_refs=fixture.artifact_refs,
            )
        )

    bundle = EvidenceJoiner().join(registry, specialist_artifacts)
    validation = EvidenceValidator().validate(bundle)
    if validation.status != "validated":
        failures.append("specialist_evidence_rejected")
    return referenced_values, failures


def _resolve_knowledge_citations(
    case: FinancialGroundingCase,
) -> tuple[list[KnowledgeEvidenceArtifact], bool]:
    by_id = {artifact.citation_id: artifact for artifact in case.knowledge_artifacts}
    resolved: list[KnowledgeEvidenceArtifact] = []
    invalid = False
    for citation_id in case.citation_ids:
        artifact = by_id.get(citation_id)
        if artifact is None:
            invalid = True
            continue
        if (
            artifact.citation_id != f"knowledge:{artifact.chunk_id}"
            or not artifact.source_url.startswith(("http://", "https://"))
            or artifact.review_after < artifact.reviewed_at
            or artifact.freshness != "current"
        ):
            invalid = True
            continue
        resolved.append(artifact)
    return resolved, invalid
