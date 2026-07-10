"""Agent loop protocol for self-hosted runtime implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.runtime.execution.context import AgentContext
from app.runtime.execution.handoff import HandoffResult
from app.runtime.execution.tool_executor import ToolObservation


@dataclass(frozen=True)
class AgentRunResult:
    reply: str
    agent_used: str
    data: dict | None = None
    tool_observations: list[ToolObservation] = field(default_factory=list)
    handoff_results: list[HandoffResult] = field(default_factory=list)


class AgentLoop(Protocol):
    """Common interface for CFO and specialist loops."""

    async def run(self, context: AgentContext) -> AgentRunResult:
        """Run one agent loop and return a typed result."""
