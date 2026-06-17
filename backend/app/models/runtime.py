"""Runtime policy models for CFO-first agent orchestration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ComplexityLevel = Literal["simple", "moderate", "complex"]
RiskLevel = Literal["low", "medium", "high"]


class RuntimePolicyResult(BaseModel):
    complexity: ComplexityLevel = "simple"
    risk_level: RiskLevel = "low"
    required_specialists: list[str] = Field(default_factory=list)
    audit_required: bool = False
    allow_market_context: bool = False
    max_tool_calls: int = Field(default=3, ge=0)
    max_deliberation_rounds: int = Field(default=0, ge=0)
