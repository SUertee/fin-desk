"""Hermetic contract grading for observable multi-agent execution facts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.turn_execution import TurnExecutionFacts


TRAJECTORY_FIXTURES = (
    Path(__file__).with_name("fixtures") / "trajectory_contract" / "cases.json"
)
TrajectoryCategory = Literal[
    "direct_response",
    "single_specialist",
    "parallel_team",
    "high_risk",
    "partial_failure",
]
StepKind = Literal["tool", "specialist", "audit", "compose"]
StepStatus = Literal["completed", "failed", "timed_out", "skipped"]
ValidationStatus = Literal["validated", "limited", "rejected"]

_SAFE_AUDIT_STATUSES = frozenset({"verified", "needs_review", "data_limited"})
_FAILED_STEP_STATUSES = frozenset({"failed", "timed_out"})


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrajectoryStep(_StrictModel):
    task_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.:-]{2,159}$")
    kind: StepKind
    status: StepStatus
    specialist: str | None = Field(default=None, max_length=80)
    depends_on: tuple[str, ...] = ()
    parallel_safe: bool = False
    projected_context_keys: tuple[str, ...] = ()
    allowed_context_keys: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_worker_identity(self) -> "TrajectoryStep":
        if self.kind in {"specialist", "audit"} and not self.specialist:
            raise ValueError("specialist and audit steps require a specialist")
        if self.kind in {"tool", "compose"} and self.specialist is not None:
            raise ValueError("tool and compose steps cannot name a specialist")
        return self


class TrajectoryContractCase(_StrictModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    category: TrajectoryCategory
    risk_level: Literal["low", "medium", "high"]
    audit_required: bool = False
    execution: TurnExecutionFacts
    steps: tuple[TrajectoryStep, ...] = ()
    available_artifacts: tuple[str, ...] = ()
    projectable_artifacts: tuple[str, ...] = ()
    accepted_specialists: tuple[str, ...] = ()
    rejected_specialists: tuple[str, ...] = ()
    final_evidence_specialists: tuple[str, ...] = ()
    validation_status: ValidationStatus | None = None
    audit_status: str | None = Field(default=None, max_length=40)
    limitations: tuple[str, ...] = ()


class TrajectoryContractResult(_StrictModel):
    case_id: str
    category: TrajectoryCategory
    passed: bool
    failures: list[str] = Field(default_factory=list, max_length=16)


class TrajectoryContractReport(_StrictModel):
    total: int
    passed: int
    results: list[TrajectoryContractResult]


def load_trajectory_contract_cases(
    path: Path = TRAJECTORY_FIXTURES,
) -> list[TrajectoryContractCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [TrajectoryContractCase.model_validate(item) for item in payload["cases"]]


def evaluate_trajectory_contract_case(
    case: TrajectoryContractCase,
) -> TrajectoryContractResult:
    failures: list[str] = []
    steps_by_id = _steps_by_id(case.steps)

    if steps_by_id is None or not _is_acyclic(case.steps):
        failures.append("invalid_dependency_graph")
        steps_by_id = {}

    if any(
        step.parallel_safe and step.kind in {"audit", "compose"}
        for step in case.steps
    ):
        failures.append("unsafe_parallel_declaration")

    if any(
        not set(step.projected_context_keys).issubset(step.allowed_context_keys)
        for step in case.steps
        if step.kind in {"specialist", "audit"}
    ):
        failures.append("context_scope_violation")

    available_refs = {
        f"artifact://{artifact_name}" for artifact_name in case.available_artifacts
    }
    if any(
        not set(step.artifact_refs).issubset(available_refs)
        for step in case.steps
    ):
        failures.append("artifact_lineage_broken")

    worker_steps = {
        step.specialist: step
        for step in case.steps
        if step.kind == "specialist" and step.specialist is not None
    }
    failed_specialists = {
        specialist
        for specialist, step in worker_steps.items()
        if step.status in _FAILED_STEP_STATUSES
    }
    completed_specialists = {
        specialist
        for specialist, step in worker_steps.items()
        if step.status == "completed"
    }
    accepted = set(case.accepted_specialists)
    rejected = set(case.rejected_specialists)
    final_evidence = set(case.final_evidence_specialists)

    if not accepted.issubset(completed_specialists):
        failures.append("failed_output_exposed")
    if final_evidence & failed_specialists or not final_evidence.issubset(accepted):
        failures.append("failed_output_exposed")
    if accepted and any(
        not set(worker_steps[specialist].artifact_refs).issubset(available_refs)
        for specialist in accepted & set(worker_steps)
    ):
        failures.append("artifact_lineage_broken")

    if case.audit_required and not _required_audit_passed(
        case,
        steps_by_id=steps_by_id,
        accepted_specialists=accepted,
        worker_steps=worker_steps,
    ):
        failures.append("missing_required_audit")

    if failed_specialists and (
        not failed_specialists.issubset(rejected)
        or not case.limitations
        or case.validation_status != "limited"
    ):
        failures.append("partial_failure_not_disclosed")

    failures.extend(_projection_failures(case))
    unique_failures = list(dict.fromkeys(failures))
    return TrajectoryContractResult(
        case_id=case.case_id,
        category=case.category,
        passed=not unique_failures,
        failures=unique_failures,
    )


def run_trajectory_contract_eval(
    cases: list[TrajectoryContractCase] | None = None,
) -> TrajectoryContractReport:
    selected_cases = cases or load_trajectory_contract_cases()
    results = [evaluate_trajectory_contract_case(case) for case in selected_cases]
    return TrajectoryContractReport(
        total=len(results),
        passed=sum(result.passed for result in results),
        results=results,
    )


def _steps_by_id(
    steps: tuple[TrajectoryStep, ...],
) -> dict[str, TrajectoryStep] | None:
    result = {step.task_id: step for step in steps}
    if len(result) != len(steps):
        return None
    task_ids = set(result)
    if any(
        dependency == step.task_id or dependency not in task_ids
        for step in steps
        for dependency in step.depends_on
    ):
        return None
    return result


def _is_acyclic(steps: tuple[TrajectoryStep, ...]) -> bool:
    dependencies = {step.task_id: set(step.depends_on) for step in steps}
    if len(dependencies) != len(steps):
        return False
    remaining = dict(dependencies)
    while remaining:
        ready = {task_id for task_id, deps in remaining.items() if not deps}
        if not ready:
            return False
        remaining = {
            task_id: deps - ready
            for task_id, deps in remaining.items()
            if task_id not in ready
        }
    return True


def _required_audit_passed(
    case: TrajectoryContractCase,
    *,
    steps_by_id: dict[str, TrajectoryStep],
    accepted_specialists: set[str],
    worker_steps: dict[str, TrajectoryStep],
) -> bool:
    audit_steps = [step for step in case.steps if step.kind == "audit"]
    if len(audit_steps) != 1:
        return False
    audit = audit_steps[0]
    required_dependencies = {
        worker_steps[specialist].task_id
        for specialist in accepted_specialists
        if specialist in worker_steps
    }
    return (
        audit.task_id in steps_by_id
        and audit.status == "completed"
        and required_dependencies.issubset(audit.depends_on)
        and case.audit_status in _SAFE_AUDIT_STATUSES
    )


def _projection_failures(case: TrajectoryContractCase) -> list[str]:
    execution = case.execution
    if execution.outcome in {"direct_response", "clarification"}:
        has_execution_surface = bool(
            case.steps
            or case.available_artifacts
            or case.accepted_specialists
            or execution.evidence_available
            or execution.specialist_findings_available
            or execution.process_available
            or execution.policy_blocked
        )
        return ["unexpected_execution_surface"] if has_execution_surface else []

    failures: list[str] = []
    if execution.outcome == "blocked" and not execution.policy_blocked:
        failures.append("execution_projection_mismatch")
    if execution.outcome != "blocked" and execution.policy_blocked:
        failures.append("execution_projection_mismatch")
    if execution.outcome == "executed":
        expected = (
            bool(case.projectable_artifacts),
            bool(case.accepted_specialists),
            bool(case.steps),
        )
        actual = (
            execution.evidence_available,
            execution.specialist_findings_available,
            execution.process_available,
        )
        if actual != expected:
            failures.append("execution_projection_mismatch")
    return failures


if __name__ == "__main__":
    print(run_trajectory_contract_eval().model_dump_json(indent=2))
