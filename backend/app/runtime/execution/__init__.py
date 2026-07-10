"""Reusable self-hosted multi-agent execution primitives."""

from app.runtime.execution.context import AgentContext
from app.runtime.execution.handoff import HandoffRequest, HandoffResult
from app.runtime.execution.loop import AgentLoop, AgentRunResult
from app.runtime.execution.planner import ExecutionPlan, PlanStep, build_execution_plan
from app.runtime.execution.state import AgentState, AgentStep
from app.runtime.execution.tool_executor import (
    BoundedToolExecutor,
    ToolObservation,
    ToolRegistry,
    ToolSpec,
)

__all__ = [
    "AgentContext",
    "AgentLoop",
    "AgentRunResult",
    "AgentState",
    "AgentStep",
    "BoundedToolExecutor",
    "ExecutionPlan",
    "HandoffRequest",
    "HandoffResult",
    "PlanStep",
    "ToolObservation",
    "ToolRegistry",
    "ToolSpec",
    "build_execution_plan",
]
