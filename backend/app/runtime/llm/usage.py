"""Usage helpers for provider adapters."""

from __future__ import annotations

from app.models.runtime import AgentRunUsage


def empty_usage() -> AgentRunUsage:
    return AgentRunUsage()
