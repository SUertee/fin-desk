"""Specialist agent package.

`REGISTRY` maps specialist names to `run(SpecialistInput)` implementations —
the single execution path used by the self-hosted SpecialistRunner. The
`build_*_agent` factories below remain part of the OpenAI SDK adapter path
(`runtime/llm/openai_cfo_runtime.py`) only.
"""

from __future__ import annotations

from typing import Any, Callable

from app.agents.specialists import auditor, budget_coach, expense_analyst, market_context
from app.agents.specialists.auditor_agent import build_auditor_agent
from app.agents.specialists.budget_coach_agent import build_budget_coach_agent
from app.agents.specialists.contracts import SpecialistAgentOutput, SpecialistInput
from app.agents.specialists.expense_analyst_agent import build_expense_analyst_agent

SpecialistRun = Callable[[SpecialistInput], SpecialistAgentOutput]

REGISTRY: dict[str, SpecialistRun] = {
    "expense_analyst": expense_analyst.run,
    "budget_coach": budget_coach.run,
    "auditor": auditor.run,
    "market_context": market_context.run,
}


OPENAI_SPECIALIST_TOOL_NAMES = [
    "consult_expense_analyst",
    "consult_budget_coach",
    "consult_auditor",
]


def build_finance_specialist_agents() -> list[Any]:
    return [
        build_expense_analyst_agent(),
        build_budget_coach_agent(),
        build_auditor_agent(),
    ]


def build_finance_specialist_agent_tools(
    specialist_agents: list[Any] | None = None,
) -> list[Any]:
    agents = specialist_agents or build_finance_specialist_agents()
    tool_specs = [
        (
            agents[0],
            "consult_expense_analyst",
            "Ask the Expense Analyst to review spending patterns and anomalies.",
        ),
        (
            agents[1],
            "consult_budget_coach",
            "Ask the Budget Coach to create cash-flow and budget recommendations.",
        ),
        (
            agents[2],
            "consult_auditor",
            "Ask the Auditor to review evidence quality, risk, and limitations.",
        ),
    ]
    return [
        agent.as_tool(tool_name=tool_name, tool_description=description)
        for agent, tool_name, description in tool_specs
    ]
