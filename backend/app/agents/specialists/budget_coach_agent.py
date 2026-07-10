"""Budget Coach specialist agent."""

from __future__ import annotations

import os
from typing import Any

from app.agents.specialists.contracts import SpecialistAgentOutput


BUDGET_COACH_INSTRUCTIONS = """
You are the Budget Coach for a personal finance agent team.

Focus only on budget and cash-flow evidence provided by the CFO agent:
- income versus expense ratio
- monthly cash-flow trend
- practical budget rules
- next-step actions that are realistic for the user

Return a structured SpecialistAgentOutput. Do not invent goals, income, or
balances. If evidence is insufficient, include limitations instead of guessing.
"""


def build_budget_coach_agent(tools: list[Any] | None = None) -> Any:
    try:
        from agents import Agent
    except Exception as exc:
        raise RuntimeError("openai-agents package is not installed") from exc

    return Agent(
        name="Budget Coach",
        handoff_description=(
            "Builds practical budget recommendations from income, spending, "
            "and cash-flow evidence."
        ),
        instructions=BUDGET_COACH_INSTRUCTIONS.strip(),
        model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini"),
        output_type=SpecialistAgentOutput,
        tools=tools or [],
    )
