"""Deterministic acceptance checks for the complete CFO runtime."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.chat import ChatResponse
from app.models.runtime import AgentRunRecord


ACCEPTANCE_FIXTURES = (
    Path(__file__).with_name("fixtures") / "cfo_runtime_acceptance" / "cases.json"
)
AcceptanceCategory = Literal[
    "conversation",
    "clarification",
    "finance_execution",
    "specialist",
    "policy",
]


class AcceptanceRuntimeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    profile: dict[str, Any] = Field(default_factory=dict)
    transactions: list[dict[str, Any]] = Field(default_factory=list)
    monthly_totals: list[dict[str, Any]] = Field(default_factory=list)
    chat_history: list[dict[str, Any]] = Field(default_factory=list)
    memory_context: dict[str, Any] = Field(default_factory=dict)
    session_id: str = ""


class AcceptanceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["direct_response", "ask_clarification", "execute"]
    reply: str | None = None
    capability_ids: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_action(self) -> "AcceptanceDecision":
        if self.action == "execute":
            if not self.capability_ids or self.reply:
                raise ValueError("execute requires capabilities and no reply")
        elif not (self.reply or "").strip() or self.capability_ids:
            raise ValueError("conversation decisions require only a reply")
        return self


class AcceptanceExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal[
        "direct_response",
        "clarification",
        "executed",
        "blocked",
        "failed",
    ]
    data_present: bool
    evidence_available: bool = False
    specialist_findings_available: bool = False
    process_available: bool = False
    policy_blocked: bool = False
    selected_agents: list[str] = Field(default_factory=list)
    required_tool_calls: list[str] = Field(default_factory=list)
    forbidden_tool_calls: list[str] = Field(default_factory=list)
    audit_status: str | None = None
    reply_contains: list[str] = Field(default_factory=list)
    reply_excludes: list[str] = Field(default_factory=list)
    enforce_numeric_grounding: bool = False


class CfoRuntimeAcceptanceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=3, max_length=100)
    category: AcceptanceCategory
    user_id: str = "acceptance-user"
    input: AcceptanceRuntimeInput
    decision: AcceptanceDecision
    granted_capabilities: list[str] | None = None
    expected: AcceptanceExpectation


class CfoRuntimeAcceptanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: AcceptanceCategory
    passed: bool
    failures: list[str] = Field(default_factory=list)


class AcceptanceCategoryScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = 0
    passed: int = 0

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


class CfoRuntimeAcceptanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    passed: int
    by_category: dict[AcceptanceCategory, AcceptanceCategoryScore]
    results: list[CfoRuntimeAcceptanceResult]

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def failures(self) -> list[CfoRuntimeAcceptanceResult]:
        return [result for result in self.results if not result.passed]


def load_cfo_runtime_acceptance_cases(
    path: Path = ACCEPTANCE_FIXTURES,
) -> list[CfoRuntimeAcceptanceCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        CfoRuntimeAcceptanceCase.model_validate(item)
        for item in payload["cases"]
    ]


def evaluate_cfo_runtime_acceptance_case(
    case: CfoRuntimeAcceptanceCase,
    response: ChatResponse | dict[str, Any],
    record: AgentRunRecord | dict[str, Any],
) -> CfoRuntimeAcceptanceResult:
    actual_response = ChatResponse.model_validate(response)
    actual_record = AgentRunRecord.model_validate(record)
    expected = case.expected
    failures: list[str] = []

    execution = actual_response.execution
    _compare(failures, "execution.outcome", execution.outcome, expected.outcome)
    _compare(
        failures,
        "execution.evidence_available",
        execution.evidence_available,
        expected.evidence_available,
    )
    _compare(
        failures,
        "execution.specialist_findings_available",
        execution.specialist_findings_available,
        expected.specialist_findings_available,
    )
    _compare(
        failures,
        "execution.process_available",
        execution.process_available,
        expected.process_available,
    )
    _compare(
        failures,
        "execution.policy_blocked",
        execution.policy_blocked,
        expected.policy_blocked,
    )
    _compare(
        failures,
        "response.data_present",
        actual_response.data is not None,
        expected.data_present,
    )
    _compare(
        failures,
        "record.selected_agents",
        actual_record.selected_agents,
        expected.selected_agents,
    )

    called_tools = {
        call.name for call in actual_record.tool_calls if call.status == "called"
    }
    for tool_name in expected.required_tool_calls:
        if tool_name not in called_tools:
            failures.append(f"missing called tool: {tool_name}")
    for tool_name in expected.forbidden_tool_calls:
        if tool_name in called_tools:
            failures.append(f"forbidden tool was called: {tool_name}")

    if expected.audit_status is not None:
        _compare(
            failures,
            "record.audit_status",
            actual_record.audit_status,
            expected.audit_status,
        )
    _compare(
        failures,
        "record.output_contract",
        actual_record.output_contract,
        "ChatResponse",
    )
    cfo_validation = next(
        (
            validation
            for validation in actual_record.output_validations
            if validation.agent == "cfo"
            and validation.contract == "ChatResponse"
        ),
        None,
    )
    if cfo_validation is None or cfo_validation.status != "passed":
        failures.append("missing passed cfo.ChatResponse validation")

    reply = actual_response.reply
    for fragment in expected.reply_contains:
        if fragment not in reply:
            failures.append(f"reply missing {fragment!r}")
    for fragment in expected.reply_excludes:
        if fragment in reply:
            failures.append(f"reply unexpectedly contains {fragment!r}")
    if expected.enforce_numeric_grounding:
        unsupported = _unsupported_reply_numbers(case, actual_response)
        if unsupported:
            failures.append(f"reply has unsupported numbers: {unsupported!r}")

    ledger_execution = actual_record.policy.get("turn_execution")
    if ledger_execution != execution.model_dump(mode="json"):
        failures.append(
            "run-ledger turn_execution does not match response execution"
        )

    return CfoRuntimeAcceptanceResult(
        case_id=case.case_id,
        category=case.category,
        passed=not failures,
        failures=failures,
    )


def build_cfo_runtime_acceptance_report(
    results: list[CfoRuntimeAcceptanceResult],
) -> CfoRuntimeAcceptanceReport:
    by_category: dict[AcceptanceCategory, AcceptanceCategoryScore] = {}
    for result in results:
        score = by_category.setdefault(
            result.category,
            AcceptanceCategoryScore(),
        )
        score.total += 1
        score.passed += int(result.passed)
    return CfoRuntimeAcceptanceReport(
        total=len(results),
        passed=sum(result.passed for result in results),
        by_category=by_category,
        results=results,
    )


def format_report(report: CfoRuntimeAcceptanceReport) -> str:
    lines = [
        f"CFO runtime acceptance: {report.passed}/{report.total} "
        f"({report.accuracy:.0%})"
    ]
    for category, score in sorted(report.by_category.items()):
        lines.append(
            f"  {category:20} {score.passed}/{score.total} "
            f"({score.accuracy:.0%})"
        )
    for result in report.failures():
        lines.append(f"  - {result.case_id}: {'; '.join(result.failures)}")
    return "\n".join(lines)


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


_NUMBER_RE = re.compile(r"(?<![\w])[-+]?\d[\d,]*(?:\.\d+)?%?")


def _unsupported_reply_numbers(
    case: CfoRuntimeAcceptanceCase,
    response: ChatResponse,
) -> list[str]:
    allowed = _collect_numbers(
        {
            "input": case.input.model_dump(mode="json"),
            "data": (
                response.data.model_dump(mode="json")
                if response.data is not None
                else None
            ),
        }
    )
    return sorted(
        {
            token
            for token in _NUMBER_RE.findall(response.reply)
            if _normalize_number(token) not in allowed
        }
    )


def _collect_numbers(value: Any) -> set[Decimal]:
    numbers: set[Decimal] = set()
    if isinstance(value, dict):
        for item in value.values():
            numbers.update(_collect_numbers(item))
    elif isinstance(value, list):
        for item in value:
            numbers.update(_collect_numbers(item))
    elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        numbers.add(Decimal(str(value)).normalize())
    elif isinstance(value, str):
        for token in _NUMBER_RE.findall(value):
            normalized = _normalize_number(token)
            if normalized is not None:
                numbers.add(normalized)
    return numbers


def _normalize_number(token: str) -> Decimal | None:
    try:
        return Decimal(token.replace(",", "").rstrip("%")).normalize()
    except InvalidOperation:
        return None
