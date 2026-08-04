"""Bounded contracts shared by FinDesk evaluation suites."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


EvalStatus = Literal["pass", "fail", "error", "skip"]
EvalSeverity = Literal["critical", "major", "advisory"]
EvalKind = Literal["capability", "regression", "holdout"]
EvalMode = Literal["offline", "live"]


class StrictEvalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalTrialLimits(StrictEvalModel):
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_steps: int = Field(default=32, ge=1, le=256)
    max_tool_calls: int = Field(default=16, ge=0, le=128)
    max_specialists: int = Field(default=8, ge=0, le=32)
    network_policy: Literal["deny", "allow"] = "deny"
    max_input_tokens: int = Field(default=0, ge=0, le=1_000_000)
    max_output_tokens: int = Field(default=0, ge=0, le=1_000_000)
    max_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)


OFFLINE_TRIAL_LIMITS = EvalTrialLimits()


class EvalTask(StrictEvalModel):
    task_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.:-]{2,159}$")
    suite_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,79}$")
    kind: EvalKind = "regression"
    fixture_ref: str = Field(min_length=1, max_length=200)
    expected_outcome: str = Field(min_length=1, max_length=80)
    required_events: list[str] = Field(default_factory=list, max_length=32)
    forbidden_events: list[str] = Field(default_factory=list, max_length=32)
    grader_ids: list[str] = Field(default_factory=list, min_length=1, max_length=16)
    severity: EvalSeverity = "major"
    tags: list[str] = Field(default_factory=list, max_length=16)
    limits: EvalTrialLimits = Field(default_factory=EvalTrialLimits)


class EvalTrial(StrictEvalModel):
    trial_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.:-]{2,199}$")
    task_id: str
    attempt: int = Field(default=1, ge=1, le=100)
    mode: EvalMode
    profile_name: str = Field(min_length=1, max_length=80)
    config_fingerprint: str = Field(pattern=r"^[a-f0-9]{12,64}$")
    status: EvalStatus
    trace_refs: list[str] = Field(default_factory=list, max_length=16)
    outcome_refs: list[str] = Field(default_factory=list, max_length=16)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)
    latency_ms: Decimal | None = Field(default=None, ge=0)


class EvalGraderResult(StrictEvalModel):
    grader_id: str = Field(min_length=3, max_length=100)
    dimension: str = Field(min_length=2, max_length=100)
    target: Literal["transcript", "outcome"]
    status: EvalStatus
    severity: EvalSeverity
    reason_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,99}$")
    detail: str = Field(default="", max_length=240)
    metric: Decimal | None = None


class EvalCaseResult(StrictEvalModel):
    suite_id: str
    case_id: str = Field(min_length=1, max_length=160)
    status: EvalStatus
    severity: EvalSeverity
    reason_codes: list[str] = Field(default_factory=list, max_length=16)
    details: list[str] = Field(default_factory=list, max_length=8)
    metrics: dict[str, Decimal] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_failure_reason(self) -> "EvalCaseResult":
        if self.status in {"fail", "error"} and not self.reason_codes:
            raise ValueError("failed eval cases require a reason code")
        if any(len(item) > 240 for item in self.details):
            raise ValueError("eval case details must be bounded")
        return self

    @property
    def stable_id(self) -> str:
        return f"{self.suite_id}:{self.case_id}"


class EvalSuiteReport(StrictEvalModel):
    suite_id: str
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    tasks: list[EvalTask]
    trials: list[EvalTrial]
    graders: list[EvalGraderResult]
    cases: list[EvalCaseResult]

    @model_validator(mode="after")
    def validate_counts(self) -> "EvalSuiteReport":
        counts = self.passed + self.failed + self.errors + self.skipped
        if counts != self.total or self.total != len(self.cases):
            raise ValueError("suite counts must agree with projected cases")
        if self.total != len(self.tasks) or self.total != len(self.trials):
            raise ValueError("each projected case requires one task and trial")
        if self.total != len(self.graders):
            raise ValueError("each projected case requires one primary grader")
        task_ids = {task.task_id for task in self.tasks}
        if {trial.task_id for trial in self.trials} != task_ids:
            raise ValueError("trials must reference the projected tasks")
        return self


class EvalBaselineCase(StrictEvalModel):
    status: EvalStatus
    severity: EvalSeverity
    required: bool = True


class EvalBaseline(StrictEvalModel):
    schema_version: Literal["1"] = "1"
    cases: dict[str, EvalBaselineCase] = Field(default_factory=dict)


class EvalCaseChange(StrictEvalModel):
    stable_id: str
    previous_status: EvalStatus | None = None
    current_status: EvalStatus | None = None
    severity: EvalSeverity
    reason_codes: list[str] = Field(default_factory=list, max_length=16)


class EvalBaselineDiff(StrictEvalModel):
    new: list[EvalCaseChange] = Field(default_factory=list)
    missing: list[EvalCaseChange] = Field(default_factory=list)
    resolved: list[EvalCaseChange] = Field(default_factory=list)
    regressed: list[EvalCaseChange] = Field(default_factory=list)


class EvalGateDecision(StrictEvalModel):
    passed: bool
    reason_codes: list[str] = Field(default_factory=list, max_length=32)


class EvalHarnessReport(StrictEvalModel):
    schema_version: Literal["1"] = "1"
    mode: Literal["offline"] = "offline"
    profile_name: Literal["offline-hermetic-v1"] = "offline-hermetic-v1"
    config_fingerprint: str = Field(pattern=r"^[a-f0-9]{12,64}$")
    suites: list[EvalSuiteReport]
    baseline_diff: EvalBaselineDiff
    gate: EvalGateDecision
