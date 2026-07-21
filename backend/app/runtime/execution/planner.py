"""Policy-driven execution planner for CFO-first finance runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.models.runtime import RuntimePolicyResult
from app.runtime.execution.context import AgentContext
from app.tools.query_tools import has_query_intent


PlanStepType = Literal["tool", "handoff", "compose"]

SPECIALIST_CAPABILITY_BY_NAME = {
    "expense_analyst": "finance.expense_review",
    "budget_coach": "finance.budget_coaching",
    "auditor": "finance.audit_review",
    "market_context": "market.context_review",
    "investment_research": "investment.research_review",
}


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
    context: AgentContext, policy: RuntimePolicyResult
) -> ExecutionPlan:
    steps = [
        PlanStep(
            step_type="tool",
            capability_id="finance.context",
            reason="baseline_finance_context",
        ),
        PlanStep(
            step_type="tool",
            capability_id="finance.import_quality",
            reason="data_quality_evidence",
        ),
    ]

    if has_query_intent(context.message):
        steps.append(
            PlanStep(
                step_type="tool",
                capability_id="finance.query_transactions",
                reason="typed_query_intent",
            )
        )

    if context.transactions:
        steps.extend(
            [
                PlanStep(
                    step_type="tool",
                    capability_id="finance.expense_snapshot",
                    reason="transaction_data_available",
                ),
                PlanStep(
                    step_type="tool",
                    capability_id="finance.anomaly_summary",
                    reason="transaction_data_available",
                ),
            ]
        )

    if context.monthly_totals:
        steps.append(
            PlanStep(
                step_type="tool",
                capability_id="finance.cashflow_summary",
                reason="monthly_totals_available",
            )
        )

    if "budget_coach" in policy.required_specialists:
        steps.append(
            PlanStep(
                step_type="tool",
                capability_id="finance.budget_snapshot",
                reason="budget_specialist_required",
            )
        )

    if "investment_research" in policy.required_specialists:
        steps.append(
            PlanStep(
                step_type="tool",
                capability_id="investment.research_context",
                reason="investment_research_specialist_required",
            )
        )

    if "market_context" in policy.required_specialists:
        steps.append(
            PlanStep(
                step_type="tool",
                capability_id="market.web_research",
                reason="market_context_specialist_required",
            )
        )

    for specialist in policy.required_specialists:
        capability_id = SPECIALIST_CAPABILITY_BY_NAME.get(specialist)
        if capability_id is None:
            raise ValueError(f"Unknown specialist capability: {specialist}")
        steps.append(
            PlanStep(
                step_type="handoff",
                capability_id=capability_id,
                reason="runtime_policy_required_specialist",
            )
        )

    if policy.audit_required:
        steps.append(
            PlanStep(
                step_type="handoff",
                capability_id=SPECIALIST_CAPABILITY_BY_NAME["auditor"],
                reason="runtime_policy_audit_required",
            )
        )

    steps.append(PlanStep(step_type="compose"))
    return ExecutionPlan(steps=steps)
