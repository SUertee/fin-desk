"""Expense Analyst specialist agent."""

from __future__ import annotations

import os
from typing import Any

from app.agents.specialists.contracts import SpecialistAgentOutput


EXPENSE_ANALYST_INSTRUCTIONS = """
You are the Expense Analyst for a personal finance agent team.

Focus only on spending evidence provided by the CFO agent:
- category concentration
- unusual or duplicate-looking expenses
- merchant-level patterns
- data limitations

Return a structured SpecialistAgentOutput. Do not invent transactions or
balances. If evidence is insufficient, include limitations instead of guessing.
"""


def build_expense_analyst_agent(tools: list[Any] | None = None) -> Any:
    try:
        from agents import Agent
    except Exception as exc:
        raise RuntimeError("openai-agents package is not installed") from exc

    return Agent(
        name="Expense Analyst",
        handoff_description=(
            "Analyzes spending categories, merchant patterns, anomalies, and "
            "expense evidence quality."
        ),
        instructions=EXPENSE_ANALYST_INSTRUCTIONS.strip(),
        model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini"),
        output_type=SpecialistAgentOutput,
        tools=tools or [],
    )
