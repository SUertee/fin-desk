"""CFO agent factory for the OpenAI Agents SDK runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


PROMPT_PATH = Path(__file__).with_name("prompt.md")


def load_cfo_instructions() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_cfo_agent(tools: list[Any] | None = None) -> Any:
    try:
        from agents import Agent
    except Exception as exc:
        raise RuntimeError("openai-agents package is not installed") from exc

    return Agent(
        name="Finance CFO",
        instructions=load_cfo_instructions(),
        model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o"),
        tools=tools or [],
    )
