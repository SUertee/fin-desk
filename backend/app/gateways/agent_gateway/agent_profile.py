"""Public profile for the Finance CFO agent."""

from __future__ import annotations

from app.gateways.agent_gateway.task_contracts import AgentCapability, AgentProfile


FINANCE_AGENT_ID = "personal-finance-cfo"


def build_finance_agent_profile() -> AgentProfile:
    """Return the protocol-neutral capability card for external agents."""

    return AgentProfile(
        agent_id=FINANCE_AGENT_ID,
        name="Personal Finance CFO Agent",
        domain="personal_finance",
        version="1.0.0",
        description=(
            "CFO-first finance workspace agent for spending review, budget planning, "
            "cash-flow reasoning, and safety-aware financial audit."
        ),
        capabilities=[
            AgentCapability(
                name="spending_review",
                title="Spending Review",
                description="Review loaded transactions and identify major spend drivers.",
                examples=["Review my June spending and highlight the largest flexible categories."],
            ),
            AgentCapability(
                name="budget_plan",
                title="Budget Plan",
                description="Create evidence-bound budget guardrails from income and expenses.",
                examples=["Build a monthly budget plan based on my current cash flow."],
            ),
            AgentCapability(
                name="cashflow_forecast",
                title="Cash-flow Forecast",
                description="Summarize cash-flow status and near-term pressure from loaded data.",
                examples=["Can I support a two-month low-income window with current spending?"],
            ),
            AgentCapability(
                name="financial_safety_audit",
                title="Financial Safety Audit",
                description="Audit finance recommendations for risk, missing data, and unsafe claims.",
                examples=["Check whether this savings plan has unsupported assumptions."],
            ),
            AgentCapability(
                name="statement_import_review",
                title="Statement Import Review",
                description="Inspect imported statement context and report data quality gaps.",
                examples=["Review whether the imported Alipay statement is complete enough."],
            ),
        ],
    )
