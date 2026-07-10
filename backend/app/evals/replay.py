"""Offline replay checks for agent harness run records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.models.runtime import AgentRunRecord, RuntimeEntrypoint, ValidationStatus


FIXTURES_DIR = Path(__file__).with_name("fixtures")


class EvalExpectation(BaseModel):
    selected_agents: list[str] = Field(default_factory=list)
    required_tool_calls: list[str] = Field(default_factory=list)
    output_validations: list["EvalOutputValidationExpectation"] = Field(default_factory=list)
    output_contract: str | None = None
    audit_status: str | None = None


class EvalOutputValidationExpectation(BaseModel):
    agent: str
    contract: str
    status: ValidationStatus = "passed"


class EvalCase(BaseModel):
    case_id: str
    entrypoint: RuntimeEntrypoint
    user_id: str
    input: dict[str, Any]
    expected: EvalExpectation


class HarnessEvalResult(BaseModel):
    case_id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)


def load_eval_cases(fixtures_dir: Path = FIXTURES_DIR) -> list[EvalCase]:
    cases = [
        EvalCase.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(fixtures_dir.glob("*.json"))
    ]
    return cases


def get_eval_case(case_id: str, fixtures_dir: Path = FIXTURES_DIR) -> EvalCase | None:
    for case in load_eval_cases(fixtures_dir):
        if case.case_id == case_id:
            return case
    return None


def evaluate_run_record(record: AgentRunRecord | dict[str, Any], case: EvalCase) -> HarnessEvalResult:
    run_record = AgentRunRecord.model_validate(record)
    failures: list[str] = []

    if run_record.entrypoint != case.entrypoint:
        failures.append(
            f"entrypoint expected {case.entrypoint}, got {run_record.entrypoint}"
        )
    if run_record.user_id != case.user_id:
        failures.append(f"user_id expected {case.user_id}, got {run_record.user_id}")

    selected_agents = set(run_record.selected_agents)
    for agent in case.expected.selected_agents:
        if agent not in selected_agents:
            failures.append(f"missing selected agent: {agent}")

    tool_call_names = {tool.name for tool in run_record.tool_calls}
    for tool_name in case.expected.required_tool_calls:
        if tool_name not in tool_call_names:
            failures.append(f"missing required tool call: {tool_name}")

    validation_index = {
        (validation.agent, validation.contract): validation
        for validation in run_record.output_validations
    }
    for expected_validation in case.expected.output_validations:
        actual_validation = validation_index.get(
            (expected_validation.agent, expected_validation.contract)
        )
        if actual_validation is None:
            failures.append(
                "missing output validation: "
                f"{expected_validation.agent}.{expected_validation.contract}"
            )
            continue
        if actual_validation.status != expected_validation.status:
            failures.append(
                "output validation "
                f"{expected_validation.agent}.{expected_validation.contract} "
                f"expected {expected_validation.status}, got {actual_validation.status}"
            )

    if (
        case.expected.output_contract
        and run_record.output_contract != case.expected.output_contract
    ):
        failures.append(
            "output_contract expected "
            f"{case.expected.output_contract}, got {run_record.output_contract}"
        )

    if case.expected.audit_status and run_record.audit_status != case.expected.audit_status:
        failures.append(
            f"audit_status expected {case.expected.audit_status}, got {run_record.audit_status}"
        )

    return HarnessEvalResult(
        case_id=case.case_id,
        passed=not failures,
        failures=failures,
    )
