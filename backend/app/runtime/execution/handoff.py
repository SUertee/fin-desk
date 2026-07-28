"""Typed internal agent-to-agent handoff contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.agents.specialists.contracts import SpecialistExecutionBudget


HandoffStatus = Literal["completed", "failed"]


@dataclass(frozen=True)
class HandoffRequest:
    from_agent: str
    to_agent: str
    task: str
    output_contract: str
    evidence: dict[str, Any] = field(default_factory=dict)
    artifact_refs: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    constraints: list[str] = field(default_factory=list)
    budget: SpecialistExecutionBudget = field(
        default_factory=SpecialistExecutionBudget
    )

    def __post_init__(self) -> None:
        if not self.from_agent.strip() or not self.to_agent.strip():
            raise ValueError("Handoff agents cannot be empty")
        if not self.task.strip():
            raise ValueError("Handoff task cannot be empty")
        if not self.output_contract.strip():
            raise ValueError("Handoff output contract cannot be empty")
        if self.output_contract != "SpecialistAgentOutput":
            raise ValueError(
                f"Unsupported handoff output contract: {self.output_contract}"
            )
        refs = tuple(dict.fromkeys(self.artifact_refs))
        if any(not ref.startswith("artifact://") for ref in refs):
            raise ValueError("Artifact references must use artifact:// identifiers")
        object.__setattr__(self, "artifact_refs", refs)
        object.__setattr__(
            self,
            "allowed_tools",
            tuple(dict.fromkeys(self.allowed_tools)),
        )
        object.__setattr__(self, "constraints", list(dict.fromkeys(self.constraints)))


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
