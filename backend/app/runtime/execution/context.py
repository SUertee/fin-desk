"""Per-run context for self-hosted agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


RuntimeEntrypoint = Literal["chat", "analyze", "workspace_brief"]


@dataclass(frozen=True)
class AgentContext:
    """Immutable inputs shared by all agents during one runtime run.

    `message` is the compatibility field every consumer already reads and
    always equals `effective_message` (the contextualized execution text).
    `raw_message` preserves the user's exact words for history/UI concerns.
    """

    request_id: str
    user_id: str
    entrypoint: RuntimeEntrypoint
    message: str
    raw_message: str = ""
    effective_message: str = ""
    profile: dict[str, Any] = field(default_factory=dict)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    monthly_totals: list[dict[str, Any]] = field(default_factory=list)
    chat_history: list[dict[str, Any]] = field(default_factory=list)
    memory_context: dict[str, Any] = field(default_factory=dict)
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Callers that only pass `message` stay coherent: both views default
        # to it, and `message` must always equal the effective text.
        if not self.raw_message:
            object.__setattr__(self, "raw_message", self.message)
        if not self.effective_message:
            object.__setattr__(self, "effective_message", self.message)
