"""Stable semantic definitions for currently registered implementations."""

from __future__ import annotations

from dataclasses import dataclass

from app.runtime.capabilities.contracts import (
    CapabilityDescriptor,
    CapabilityExecutionMode,
    CapabilityKind,
    CapabilityRiskLevel,
)


@dataclass(frozen=True)
class CapabilityDefinition:
    capability_id: str
    kind: CapabilityKind
    title: str
    owner: str
    risk_level: CapabilityRiskLevel
    execution_mode: CapabilityExecutionMode
    input_contract: str
    output_contract: str
    description: str = ""

    def descriptor(self, *, fallback_description: str = "") -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=self.capability_id,
            kind=self.kind,
            title=self.title,
            description=self.description or fallback_description,
            owner=self.owner,
            risk_level=self.risk_level,
            execution_mode=self.execution_mode,
            input_contract=self.input_contract,
            output_contract=self.output_contract,
        )


def _tool(
    capability_id: str,
    title: str,
    *,
    owner: str = "finance",
    risk_level: CapabilityRiskLevel = "low",
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        kind="tool",
        title=title,
        owner=owner,
        risk_level=risk_level,
        execution_mode="read_only",
        input_contract="AgentContextPayload",
        output_contract="ToolObservation",
    )


TOOL_CAPABILITY_DEFINITIONS: dict[str, CapabilityDefinition] = {
    "get_finance_context": _tool("finance.context", "Finance context"),
    "get_expense_snapshot": _tool("finance.expense_snapshot", "Expense snapshot"),
    "get_budget_snapshot": _tool("finance.budget_snapshot", "Budget snapshot"),
    "get_anomaly_summary": _tool("finance.anomaly_summary", "Anomaly summary"),
    "get_cashflow_summary": _tool("finance.cashflow_summary", "Cash-flow summary"),
    "get_import_quality_report": _tool(
        "finance.import_quality", "Statement import quality"
    ),
    "query_transactions": _tool(
        "finance.query_transactions", "Typed transaction query"
    ),
    "get_investment_research_context": _tool(
        "investment.research_context",
        "Investment research context",
        owner="investment_research",
        risk_level="medium",
    ),
    "search_web_research": _tool(
        "market.web_research",
        "Governed web research",
        owner="market_context",
        risk_level="medium",
    ),
}


def _agent(
    capability_id: str,
    title: str,
    description: str,
    *,
    owner: str,
    risk_level: CapabilityRiskLevel = "low",
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        kind="agent",
        title=title,
        description=description,
        owner=owner,
        risk_level=risk_level,
        execution_mode="analysis",
        input_contract="SpecialistInput",
        output_contract="SpecialistAgentOutput",
    )


SPECIALIST_CAPABILITY_DEFINITIONS: dict[str, CapabilityDefinition] = {
    "expense_analyst": _agent(
        "finance.expense_review",
        "Expense review",
        "Review spending structure, anomalies, and controllable expenses.",
        owner="expense_analyst",
    ),
    "budget_coach": _agent(
        "finance.budget_coaching",
        "Budget coaching",
        "Evaluate cash flow, budget pressure, and savings actions.",
        owner="budget_coach",
    ),
    "auditor": _agent(
        "finance.audit_review",
        "Finance audit review",
        "Review evidence quality, limitations, and recommendation risk.",
        owner="auditor",
        risk_level="medium",
    ),
    "market_context": _agent(
        "market.context_review",
        "Market context review",
        "Interpret governed and sourced market context without trade execution.",
        owner="market_context",
        risk_level="medium",
    ),
    "investment_research": _agent(
        "investment.research_review",
        "Investment research review",
        "Produce read-only research from bounded market evidence.",
        owner="investment_research",
        risk_level="medium",
    ),
}
