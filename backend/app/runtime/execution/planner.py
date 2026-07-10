"""Policy-driven execution planner for CFO-first finance runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.models.runtime import RuntimePolicyResult
from app.runtime.execution.context import AgentContext
from app.tools.query_tools import has_query_intent


PlanStepType = Literal["tool", "handoff", "compose"]


@dataclass(frozen=True)
class PlanStep:
    step_type: PlanStepType
    name: str
    agent: str = "cfo"
    reason: str = ""


@dataclass(frozen=True)
class ExecutionPlan:
    selected_agents: list[str]
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def tool_names(self) -> list[str]:
        return [step.name for step in self.steps if step.step_type == "tool"]


def _selected_agents(policy: RuntimePolicyResult) -> list[str]:
    agents = ["cfo", *policy.required_specialists]
    if policy.audit_required:
        agents.append("auditor")
    return list(dict.fromkeys(agents))


def build_execution_plan(context: AgentContext, policy: RuntimePolicyResult) -> ExecutionPlan:
    steps = [
        PlanStep(
            step_type="tool",
            name="get_finance_context",
            reason="baseline_finance_context",
        ),
        PlanStep(
            step_type="tool",
            name="get_import_quality_report",
            reason="data_quality_evidence",
        ),
    ]

    if has_query_intent(context.message):
        steps.append(
            PlanStep(
                step_type="tool",
                name="query_transactions",
                reason="typed_query_intent",
            )
        )

    if context.transactions:
        steps.extend(
            [
                PlanStep(
                    step_type="tool",
                    name="get_expense_snapshot",
                    reason="transaction_data_available",
                ),
                PlanStep(
                    step_type="tool",
                    name="get_anomaly_summary",
                    reason="transaction_data_available",
                ),
            ]
        )

    if context.monthly_totals:
        steps.append(
            PlanStep(
                step_type="tool",
                name="get_cashflow_summary",
                reason="monthly_totals_available",
            )
        )

    if "budget_coach" in policy.required_specialists:
        steps.append(
            PlanStep(
                step_type="tool",
                name="get_budget_snapshot",
                reason="budget_specialist_required",
            )
        )

    for specialist in policy.required_specialists:
        steps.append(
            PlanStep(
                step_type="handoff",
                name=specialist,
                reason="runtime_policy_required_specialist",
            )
        )

    if policy.audit_required:
        steps.append(
            PlanStep(
                step_type="handoff",
                name="auditor",
                reason="runtime_policy_audit_required",
            )
        )

    steps.append(PlanStep(step_type="compose", name="final_response"))
    return ExecutionPlan(selected_agents=_selected_agents(policy), steps=steps)
