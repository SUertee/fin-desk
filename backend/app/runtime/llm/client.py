"""Minimal provider client protocol used by future LLM-backed agent steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.models.runtime import AgentRunUsage


@dataclass(frozen=True)
class LLMResponse:
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    usage: AgentRunUsage = field(default_factory=AgentRunUsage)
    model_name: str | None = None


class LLMClient(Protocol):
    async def generate_text(self, prompt: str, *, profile: str = "chat") -> LLMResponse:
        """Generate text without owning agent orchestration."""

    async def generate_json(
        self,
        prompt: str,
        *,
        profile: str = "chat",
    ) -> LLMResponse:
        """Generate JSON-like content without owning agent orchestration."""
