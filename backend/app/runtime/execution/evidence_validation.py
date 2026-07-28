"""Join and structurally validate current-run evidence before audit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.agents.specialists.contracts import SpecialistAgentOutput
from app.runtime.execution.artifact_registry import ArtifactRegistry


EvidenceValidationStatus = Literal["validated", "limited", "rejected"]


@dataclass(frozen=True)
class SpecialistArtifact:
    specialist: str
    output: SpecialistAgentOutput
    artifact_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceBundle:
    tool_artifacts: dict[str, Any]
    specialist_artifacts: tuple[SpecialistArtifact, ...]

    def outputs_for(
        self,
        specialists: tuple[str, ...],
    ) -> dict[str, SpecialistAgentOutput]:
        accepted = set(specialists)
        return {
            artifact.specialist: artifact.output
            for artifact in self.specialist_artifacts
            if artifact.specialist in accepted
        }


@dataclass(frozen=True)
class EvidenceValidationResult:
    status: EvidenceValidationStatus
    accepted_specialists: tuple[str, ...]
    rejected_specialists: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def ledger_dump(self) -> dict[str, Any]:
        return {
            "stage": "evidence_validation",
            "status": self.status,
            "accepted_specialists": list(self.accepted_specialists),
            "rejected_specialists": list(self.rejected_specialists),
            "reason_codes": list(self.reason_codes),
        }


class EvidenceJoiner:
    """Create one immutable view over current-run evidence."""

    def join(
        self,
        artifacts: ArtifactRegistry,
        specialist_artifacts: list[SpecialistArtifact],
    ) -> EvidenceBundle:
        return EvidenceBundle(
            tool_artifacts=artifacts.as_dict(),
            specialist_artifacts=tuple(specialist_artifacts),
        )


class EvidenceValidator:
    """Reject malformed specialist evidence without judging its meaning."""

    def validate(self, bundle: EvidenceBundle) -> EvidenceValidationResult:
        accepted: list[str] = []
        rejected: list[str] = []
        reasons: list[str] = []

        for artifact in bundle.specialist_artifacts:
            artifact_reasons = self._validate_specialist(
                artifact,
                tool_artifacts=bundle.tool_artifacts,
            )
            if artifact_reasons:
                rejected.append(artifact.specialist)
                reasons.extend(artifact_reasons)
            else:
                accepted.append(artifact.specialist)

        if not rejected:
            status: EvidenceValidationStatus = "validated"
        elif accepted or bundle.tool_artifacts:
            status = "limited"
        else:
            status = "rejected"

        return EvidenceValidationResult(
            status=status,
            accepted_specialists=tuple(accepted),
            rejected_specialists=tuple(rejected),
            reason_codes=tuple(reasons[:20]),
        )

    @staticmethod
    def _validate_specialist(
        artifact: SpecialistArtifact,
        *,
        tool_artifacts: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        for ref in artifact.artifact_refs:
            if not ref.startswith("artifact://"):
                reasons.append(
                    f"invalid_artifact_ref:{artifact.specialist}"
                )
                continue
            artifact_name = ref.removeprefix("artifact://")
            if not artifact_name or artifact_name not in tool_artifacts:
                reasons.append(
                    "missing_artifact_ref:"
                    f"{artifact.specialist}:{artifact_name or 'empty'}"
                )

        for index, finding in enumerate(artifact.output.findings):
            if not any(item.strip() for item in finding.evidence):
                reasons.append(
                    f"finding_without_evidence:{artifact.specialist}:{index}"
                )
            has_url = bool((finding.source_url or "").strip())
            has_published_at = bool((finding.published_at or "").strip())
            if has_url != has_published_at:
                reasons.append(
                    f"incomplete_external_source:{artifact.specialist}:{index}"
                )
        return reasons
