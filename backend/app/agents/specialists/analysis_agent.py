"""Analysis specialist agent factory for the OpenAI Agents SDK runtime."""

from __future__ import annotations

import os
from typing import Any


ANALYSIS_AGENT_INSTRUCTIONS = """
You are a personal finance analysis specialist.

Return only valid JSON with this exact shape:
{
  "insights": ["short evidence-backed insight"],
  "actions": ["specific next action"],
  "budget": {
    "rules": ["budget rule"],
    "monthly_targets": {"category": number}
  },
  "notes": "short caveat or empty string"
}

Rules:
- Use only the evidence provided in the input payload.
- Do not invent transactions, income, debts, or account balances.
- Keep insights and actions concise, concrete, and user-facing.
- If the evidence is limited, say so in notes.
- Do not include markdown, code fences, or prose outside the JSON object.
"""


def build_analysis_agent(tools: list[Any] | None = None) -> Any:
    try:
        from agents import Agent
    except Exception as exc:
        raise RuntimeError("openai-agents package is not installed") from exc

    return Agent(
        name="Finance Analysis Specialist",
        instructions=ANALYSIS_AGENT_INSTRUCTIONS.strip(),
        model=os.getenv("OPENAI_ANALYSIS_MODEL")
        or os.getenv("OPENAI_AGENT_MODEL", "gpt-4o"),
        tools=tools or [],
    )
