"""Auditor specialist agent."""

from __future__ import annotations

import os
from typing import Any

from app.agents.specialists.contracts import SpecialistAgentOutput


AUDITOR_INSTRUCTIONS = """
You are the Auditor for a personal finance agent team.

Review the CFO and specialist evidence for:
- unsupported claims
- missing transaction or monthly trend context
- investment or high-risk financial advice
- overconfident recommendations

Return a structured SpecialistAgentOutput with limitations and warnings. Do not
provide investment, tax, legal, or guaranteed-return advice.
"""


def build_auditor_agent(tools: list[Any] | None = None) -> Any:
    try:
        from agents import Agent
    except Exception as exc:
        raise RuntimeError("openai-agents package is not installed") from exc

    return Agent(
        name="Finance Auditor",
        handoff_description=(
            "Checks evidence quality, unsupported claims, high-risk advice, "
            "and audit limitations."
        ),
        instructions=AUDITOR_INSTRUCTIONS.strip(),
        model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini"),
        output_type=SpecialistAgentOutput,
        tools=tools or [],
    )
