"""Typed contracts for specialist finance agents.

`SpecialistInput` is the single input shape every specialist run-module
consumes; `SpecialistAgentOutput` is the single output contract the
SpecialistRunner validates. Externally grounded findings (market context)
carry `source_url`/`published_at`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SpecialistName = Literal[
    "expense_analyst",
    "budget_coach",
    "auditor",
    "market_context",
    "investment_research",
]
RiskLevel = Literal["low", "medium", "high"]


class SpecialistFinding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    evidence: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "low"
    source_url: str | None = None
    published_at: str | None = None


class SpecialistRecommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    rationale: str
    next_step: str


class SpecialistExecutionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tool_calls: int = Field(default=0, ge=0, le=8)
    max_output_tokens: int = Field(default=1200, ge=1, le=8000)
    timeout_ms: int = Field(default=5000, ge=100, le=60000)


class SpecialistAgentOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    specialist: SpecialistName
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[SpecialistFinding] = Field(default_factory=list)
    recommendations: list[SpecialistRecommendation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class SpecialistInput(BaseModel):
    """Uniform input assembled by the SpecialistRunner from a HandoffRequest."""

    model_config = ConfigDict(extra="ignore")

    task: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    constraints: list[str] = Field(default_factory=list)
    budget: SpecialistExecutionBudget = Field(
        default_factory=SpecialistExecutionBudget
    )
    policy: dict[str, Any] = Field(default_factory=dict)
    prior_outputs: dict[str, SpecialistAgentOutput] = Field(default_factory=dict)
