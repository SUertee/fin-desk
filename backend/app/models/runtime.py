"""Runtime policy and harness models for CFO-first agent orchestration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ComplexityLevel = Literal["simple", "moderate", "complex"]
RiskLevel = Literal["low", "medium", "high"]
RuntimeEntrypoint = Literal["chat", "analyze", "workspace_brief"]
ToolCallStatus = Literal["expected", "called", "failed", "skipped"]
HandoffStatus = Literal["planned", "completed", "failed"]
ValidationStatus = Literal["passed", "failed"]


class RuntimePolicyResult(BaseModel):
    complexity: ComplexityLevel = "simple"
    risk_level: RiskLevel = "low"
    required_specialists: list[str] = Field(default_factory=list)
    audit_required: bool = False
    allow_market_context: bool = False
    max_tool_calls: int = Field(default=3, ge=0)
    max_deliberation_rounds: int = Field(default=0, ge=0)


class AgentInputSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_length: int = Field(default=0, ge=0)
    transaction_count: int = Field(default=0, ge=0)
    monthly_total_count: int = Field(default=0, ge=0)
    anomaly_count: int = Field(default=0, ge=0)
    chat_history_count: int = Field(default=0, ge=0)
    memory_recent_turns_count: int = Field(default=0, ge=0)
    memory_session_state_present: bool = False
    memory_truncated: bool = False
    memory_summary_used: bool = False


class AgentToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    status: ToolCallStatus = "expected"
    agent: str | None = None
    latency_ms: float | None = Field(default=None, ge=0)


class AgentHandoff(BaseModel):
    model_config = ConfigDict(extra="ignore")

    from_agent: str
    to_agent: str
    status: HandoffStatus = "planned"
    reason: str | None = None
    # Bounded specialist output for evidence projection (findings,
    # recommendations, limitations) — never raw payloads.
    output: dict | None = None


class AgentOutputValidation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent: str
    contract: str
    status: ValidationStatus = "passed"
    errors: list[str] = Field(default_factory=list)


class AgentRunUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_count: int = Field(default=0, ge=0)
    model_response_count: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class AgentRunCost(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model_name: str | None = None
    currency: str = "USD"
    input_cost_per_1m: float | None = Field(default=None, ge=0)
    output_cost_per_1m: float | None = Field(default=None, ge=0)
    estimated_input_cost: float = Field(default=0, ge=0)
    estimated_output_cost: float = Field(default=0, ge=0)
    estimated_total_cost: float = Field(default=0, ge=0)
    pricing_source: str = "not_configured"


class AgentRunRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "agent-run-record/v1"
    request_id: str
    entrypoint: RuntimeEntrypoint
    user_id: str
    runtime_requested: str
    runtime_used: str | None = None
    model_name: str | None = None
    selected_agents: list[str] = Field(default_factory=list)
    tools_available: list[str] = Field(default_factory=list)
    tool_calls: list[AgentToolCall] = Field(default_factory=list)
    handoffs: list[AgentHandoff] = Field(default_factory=list)
    output_validations: list[AgentOutputValidation] = Field(default_factory=list)
    output_contract: str | None = None
    audit_status: str | None = None
    input_summary: AgentInputSummary = Field(default_factory=AgentInputSummary)
    policy: dict[str, Any] = Field(default_factory=dict)
    usage: AgentRunUsage = Field(default_factory=AgentRunUsage)
    cost: AgentRunCost = Field(default_factory=AgentRunCost)
    latency_ms: float = Field(ge=0)
    error_type: str | None = None
