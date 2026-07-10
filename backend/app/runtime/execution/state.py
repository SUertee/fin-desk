"""Mutable execution state for a single agent run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.runtime.execution.handoff import HandoffResult
from app.runtime.execution.tool_executor import ToolObservation


StepStatus = Literal["planned", "running", "completed", "failed"]


@dataclass
class AgentStep:
    index: int
    agent: str
    action: str
    status: StepStatus = "planned"
    reason: str = ""
    latency_ms: float | None = None


@dataclass
class AgentState:
    """Canonical in-memory state. Persistence happens through the run ledger."""

    selected_agents: list[str] = field(default_factory=list)
    planned_steps: list[AgentStep] = field(default_factory=list)
    tool_observations: list[ToolObservation] = field(default_factory=list)
    handoff_results: list[HandoffResult] = field(default_factory=list)
    final_answer: str = ""
    error_type: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def record_tool_observation(self, observation: ToolObservation) -> None:
        self.tool_observations.append(observation)

    def record_handoff_result(self, result: HandoffResult) -> None:
        self.handoff_results.append(result)
