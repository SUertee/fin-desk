"""Per-run context for self-hosted agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


RuntimeEntrypoint = Literal["chat", "workspace_brief"]


@dataclass(frozen=True)
class AgentContext:
    """Immutable raw and contextualized inputs shared during one run."""

    request_id: str
    user_id: str
    entrypoint: RuntimeEntrypoint
    raw_message: str
    effective_message: str
    profile: dict[str, Any] = field(default_factory=dict)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    monthly_totals: list[dict[str, Any]] = field(default_factory=list)
    chat_history: list[dict[str, Any]] = field(default_factory=list)
    memory_context: dict[str, Any] = field(default_factory=dict)
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
