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
    constraints: list[str] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)
    prior_outputs: dict[str, SpecialistAgentOutput] = Field(default_factory=dict)
