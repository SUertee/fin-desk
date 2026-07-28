"""Deterministic execution plan for validated capability requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from app.models.runtime import RuntimePolicyResult
from app.runtime.execution.team_expansion import expand_team_capabilities

if TYPE_CHECKING:
    from app.runtime.capabilities.catalog import CapabilityCatalog


PlanStepType = Literal["tool", "handoff", "compose"]


@dataclass(frozen=True)
class PlanStep:
    step_type: PlanStepType
    capability_id: str | None = None
    agent: str = "cfo"
    reason: str = ""


@dataclass(frozen=True)
class ExecutionPlan:
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def tool_capability_ids(self) -> list[str]:
        return [
            step.capability_id
            for step in self.steps
            if step.step_type == "tool" and step.capability_id is not None
        ]

    @property
    def handoff_capability_ids(self) -> list[str]:
        return [
            step.capability_id
            for step in self.steps
            if step.step_type == "handoff" and step.capability_id is not None
        ]

    @property
    def capability_ids(self) -> frozenset[str]:
        return frozenset([*self.tool_capability_ids, *self.handoff_capability_ids])


def build_execution_plan(
    capability_ids: tuple[str, ...] | list[str],
    policy: RuntimePolicyResult,
    catalog: "CapabilityCatalog",
) -> ExecutionPlan:
    """Expand agent evidence dependencies without interpreting user text."""

    requested = expand_team_capabilities(capability_ids, catalog)
    tools: list[str] = []
    agents: list[str] = []
    for capability_id in requested:
        entry = catalog.get(capability_id)
        if entry is None:
            raise ValueError(f"Unknown capability id: {capability_id}")
        if entry.descriptor.kind == "tool":
            tools.append(capability_id)
        elif entry.descriptor.kind == "agent":
            agents.append(capability_id)
            dependencies = entry.descriptor.requires
            if (
                capability_id == "investment.research_review"
                and "investment.external_market_history" in requested
            ):
                dependencies = ()
            tools.extend(dependencies)
        else:
            raise ValueError(f"Unsupported executable capability kind: {capability_id}")

    if policy.audit_required and "finance.audit_review" not in agents:
        agents.append("finance.audit_review")

    steps = [
        PlanStep("tool", capability_id, reason="capability_dependency")
        for capability_id in dict.fromkeys(tools)
    ]
    steps.extend(
        PlanStep("handoff", capability_id, reason="cfo_capability_request")
        for capability_id in dict.fromkeys(agents)
    )
    steps.append(PlanStep("compose"))
    return ExecutionPlan(steps=steps)
