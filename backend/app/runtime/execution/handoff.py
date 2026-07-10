"""Typed internal agent-to-agent handoff contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


HandoffStatus = Literal["completed", "failed"]


@dataclass(frozen=True)
class HandoffRequest:
    from_agent: str
    to_agent: str
    task: str
    evidence: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    output_contract: str = ""


@dataclass(frozen=True)
class HandoffResult:
    from_agent: str
    to_agent: str
    status: HandoffStatus
    output: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    limitations: list[str] = field(default_factory=list)
    error_message: str = ""
    latency_ms: float | None = None
