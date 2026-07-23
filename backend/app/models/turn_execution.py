"""Public facts describing what happened during one CFO turn."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


TurnOutcome = Literal[
    "direct_response",
    "clarification",
    "executed",
    "blocked",
    "failed",
]


class TurnExecutionFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    outcome: TurnOutcome
    evidence_available: bool = False
    specialist_findings_available: bool = False
    process_available: bool = False
    policy_blocked: bool = False
