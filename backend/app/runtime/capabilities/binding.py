"""Pre-execution binding from semantic plan steps to registry references."""

from __future__ import annotations

from collections.abc import Set
from dataclasses import dataclass
from typing import Literal

from app.runtime.capabilities.resolver import CapabilityResolver
from app.runtime.execution.planner import ExecutionPlan


BoundStepType = Literal["tool", "handoff"]


class CapabilityBindingError(RuntimeError):
    def __init__(self, capability_id: str, status: str, reason: str):
        self.capability_id = capability_id
        self.status = status
        self.reason = reason
        super().__init__(
            f"Capability binding failed for {capability_id}: {status} ({reason})"
        )


@dataclass(frozen=True)
class BoundCapabilityStep:
    step_type: BoundStepType
    capability_id: str
    registry_name: str
    agent: str = "cfo"
    reason: str = ""


@dataclass(frozen=True)
class BoundExecutionPlan:
    selected_agents: tuple[str, ...]
    steps: tuple[BoundCapabilityStep, ...]

    @property
    def tool_names(self) -> list[str]:
        return [step.registry_name for step in self.steps if step.step_type == "tool"]

    @property
    def handoff_names(self) -> list[str]:
        return [
            step.registry_name for step in self.steps if step.step_type == "handoff"
        ]


def bind_execution_plan(
    plan: ExecutionPlan,
    resolver: CapabilityResolver,
    *,
    granted_capabilities: Set[str],
) -> BoundExecutionPlan:
    """Resolve every executable step before any implementation can run."""

    bound_steps: list[BoundCapabilityStep] = []
    for step in plan.steps:
        if step.step_type == "compose":
            continue
        if step.capability_id is None:
            raise CapabilityBindingError(
                "missing", "unknown", "Plan step has no capability id"
            )
        expected_kind = "tool" if step.step_type == "tool" else "agent"
        resolution = resolver.resolve(
            step.capability_id,
            granted_capabilities=granted_capabilities,
            expected_kind=expected_kind,
        )
        if resolution.status != "resolved" or resolution.reference is None:
            raise CapabilityBindingError(
                step.capability_id,
                resolution.status,
                resolution.reason,
            )
        bound_steps.append(
            BoundCapabilityStep(
                step_type=step.step_type,
                capability_id=step.capability_id,
                registry_name=resolution.reference.registry_name,
                agent=step.agent,
                reason=step.reason,
            )
        )
    selected_agents = tuple(
        dict.fromkeys(
            [
                "cfo",
                *[
                    step.registry_name
                    for step in bound_steps
                    if step.step_type == "handoff"
                ],
            ]
        )
    )
    return BoundExecutionPlan(selected_agents=selected_agents, steps=tuple(bound_steps))
