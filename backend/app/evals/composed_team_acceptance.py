"""Offline acceptance checks for composed specialist teams."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.specialists.contracts import SpecialistInput, SpecialistName
from app.models.chat import ChatResponse
from app.models.runtime import AgentRunRecord
from app.runtime.execution.handoff_scheduler import ScheduledTaskStatus


FIXTURE = (
    Path(__file__).with_name("fixtures")
    / "composed_team_acceptance"
    / "cases.json"
)


class ComposedTeamRuntimeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    profile: dict[str, Any] = Field(default_factory=dict)
    transactions: list[dict[str, Any]] = Field(default_factory=list)
    monthly_totals: list[dict[str, Any]] = Field(default_factory=list)


class ComposedTeamExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_agents: list[str]
    schedule_statuses: dict[SpecialistName, ScheduledTaskStatus]
    accepted_specialists: list[SpecialistName]
    rejected_specialists: list[SpecialistName]
    context_keys: dict[SpecialistName, list[str]]
    artifact_refs: dict[SpecialistName, list[str]]
    auditor_prior_outputs: list[SpecialistName]
    limitation_fragment: str | None = None


class ComposedTeamAcceptanceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=3, max_length=100)
    team_capability_id: str = Field(pattern=r"^team\.")
    failing_specialists: list[SpecialistName] = Field(default_factory=list)
    input: ComposedTeamRuntimeInput
    expected: ComposedTeamExpectation


class ComposedTeamAcceptanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)


class ComposedTeamAcceptanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    results: list[ComposedTeamAcceptanceResult]

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


def load_composed_team_acceptance_cases(
    path: Path = FIXTURE,
) -> list[ComposedTeamAcceptanceCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        ComposedTeamAcceptanceCase.model_validate(item)
        for item in payload["cases"]
    ]


def evaluate_composed_team_acceptance_case(
    case: ComposedTeamAcceptanceCase,
    response: ChatResponse | dict[str, Any],
    record: AgentRunRecord | dict[str, Any],
    captured_inputs: dict[str, SpecialistInput],
) -> ComposedTeamAcceptanceResult:
    actual_response = ChatResponse.model_validate(response)
    actual_record = AgentRunRecord.model_validate(record)
    expected = case.expected
    failures: list[str] = []

    _compare(
        failures,
        "selected_agents",
        actual_record.selected_agents,
        expected.selected_agents,
    )
    execution = actual_response.execution
    if execution.outcome != "executed":
        failures.append(
            f"execution.outcome={execution.outcome!r}, expected 'executed'"
        )
    if not execution.evidence_available:
        failures.append("public execution facts omit tool evidence")
    if not execution.specialist_findings_available:
        failures.append("public execution facts omit specialist findings")
    if not execution.process_available:
        failures.append("public execution facts omit execution process")
    if (
        actual_record.policy.get("turn_execution")
        != execution.model_dump(mode="json")
    ):
        failures.append("ledger and public execution facts disagree")

    scheduling = actual_record.policy.get("specialist_execution") or {}
    schedule_statuses = {
        task.get("specialist"): task.get("status")
        for task in scheduling.get("tasks") or []
    }
    _compare(
        failures,
        "schedule_statuses",
        schedule_statuses,
        dict(expected.schedule_statuses),
    )
    if any(
        not task.get("parallel_safe")
        for task in scheduling.get("tasks") or []
    ):
        failures.append("team worker was not marked parallel_safe")

    validation = actual_record.policy.get("evidence_validation") or {}
    _compare(
        failures,
        "accepted_specialists",
        validation.get("accepted_specialists"),
        list(expected.accepted_specialists),
    )
    _compare(
        failures,
        "rejected_specialists",
        validation.get("rejected_specialists"),
        list(expected.rejected_specialists),
    )

    sensitive_keys = {
        "profile",
        "chat_history",
        "memory_context",
        "transactions",
        "transactions_sample",
    }
    for specialist, expected_keys in expected.context_keys.items():
        specialist_input = captured_inputs.get(specialist)
        if specialist_input is None:
            failures.append(f"missing captured input: {specialist}")
            continue
        _compare(
            failures,
            f"{specialist}.context_keys",
            sorted(specialist_input.evidence),
            sorted(expected_keys),
        )
        _compare(
            failures,
            f"{specialist}.artifact_refs",
            list(specialist_input.artifact_refs),
            expected.artifact_refs.get(specialist, []),
        )
        if specialist_input.allowed_tools:
            failures.append(f"{specialist} received an unexpected tool allowlist")
        if specialist_input.budget.max_tool_calls != 0:
            failures.append(f"{specialist} received a non-zero tool budget")
        if sensitive_keys.intersection(specialist_input.evidence):
            failures.append(f"{specialist} received unprojected private context")

    auditor_input = captured_inputs.get("auditor")
    if auditor_input is None:
        failures.append("auditor input was not captured")
    else:
        _compare(
            failures,
            "auditor_prior_outputs",
            list(auditor_input.prior_outputs),
            list(expected.auditor_prior_outputs),
        )

    handoff_order = [item.to_agent for item in actual_record.handoffs]
    if not handoff_order or handoff_order[-1] != "auditor":
        failures.append("auditor did not execute after team workers")

    validation_by_agent = {
        item.agent: item.status for item in actual_record.output_validations
    }
    for specialist in expected.accepted_specialists:
        if validation_by_agent.get(specialist) != "passed":
            failures.append(f"{specialist} output contract did not pass")
    for specialist in expected.rejected_specialists:
        if validation_by_agent.get(specialist) != "failed":
            failures.append(f"{specialist} output contract was not rejected")

    data = actual_response.data
    if data is None or data.audit is None:
        failures.append("response omitted typed audit data")
    elif expected.limitation_fragment:
        warnings = data.audit.warnings or []
        if not any(
            expected.limitation_fragment in warning
            for warning in warnings
        ):
            failures.append("response audit omitted partial-team limitation")
        if expected.limitation_fragment not in actual_response.reply:
            failures.append("reply omitted partial-team limitation")

    return ComposedTeamAcceptanceResult(
        case_id=case.case_id,
        passed=not failures,
        failures=failures,
    )


def build_composed_team_acceptance_report(
    results: list[ComposedTeamAcceptanceResult],
) -> ComposedTeamAcceptanceReport:
    return ComposedTeamAcceptanceReport(
        total=len(results),
        passed=sum(item.passed for item in results),
        results=results,
    )


def _compare(
    failures: list[str],
    field_name: str,
    actual: Any,
    expected: Any,
) -> None:
    if actual != expected:
        failures.append(
            f"{field_name}={actual!r}, expected {expected!r}"
        )
