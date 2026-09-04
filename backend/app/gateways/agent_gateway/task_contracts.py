"""Protocol-neutral contracts for agent-to-agent finance tasks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AgentCapabilityName = Literal[
    "spending_review",
    "budget_plan",
    "cashflow_forecast",
    "financial_safety_audit",
    "statement_import_review",
]
AgentTaskStatus = Literal["completed", "failed"]
AgentTaskPriority = Literal["low", "normal", "high"]


class AgentCapability(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: AgentCapabilityName
    title: str
    description: str
    input_contract: str = "AgentTaskRequest"
    output_contract: str = "AgentTaskResponse"
    examples: list[str] = Field(default_factory=list)


class AgentProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_id: str
    name: str
    domain: str
    version: str
    description: str
    owner: str = "fin-desk"
    default_entrypoint: str = "/agent-gateway/tasks"
    capabilities: list[AgentCapability]
    supported_protocols: list[str] = Field(default_factory=lambda: ["agent_gateway/v1"])


class AgentTaskRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_id: str | None = Field(default=None, description="Caller supplied idempotency key.")
    user_id: str = "demo"
    requester_agent: str | None = None
    capability: AgentCapabilityName
    message: str = Field(min_length=1)
    priority: AgentTaskPriority = "normal"
    context: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class AgentTaskResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ok: bool
    task_id: str
    status: AgentTaskStatus
    agent_id: str = "personal-finance-cfo"
    capability: AgentCapabilityName
    requester_agent: str | None = None
    correlation_id: str | None = None
    reply: str = ""
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
