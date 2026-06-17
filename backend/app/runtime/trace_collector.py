"""Structured trace metadata for finance agent runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import uuid4


@dataclass
class TraceCollector:
    user_id: str
    runtime_requested: str
    request_id: str = field(default_factory=lambda: str(uuid4()))
    runtime_used: str | None = None
    error_type: str | None = None
    policy: dict[str, Any] = field(default_factory=dict)
    tools_available: list[str] = field(default_factory=list)
    _started_at: float = field(default_factory=perf_counter)

    @classmethod
    def start_run(cls, *, user_id: str, runtime_requested: str) -> "TraceCollector":
        return cls(user_id=user_id, runtime_requested=runtime_requested)

    def set_policy(self, policy: dict[str, Any]) -> None:
        self.policy = policy

    def set_tools_available(self, tools: list[str]) -> None:
        self.tools_available = tools

    def mark_runtime_used(self, runtime: str) -> None:
        self.runtime_used = runtime

    def fail(self, error: Exception) -> None:
        self.error_type = type(error).__name__

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "runtime_requested": self.runtime_requested,
            "runtime_used": self.runtime_used,
            "policy": self.policy,
            "tools_available": self.tools_available,
            "latency_ms": round((perf_counter() - self._started_at) * 1000, 2),
            "error_type": self.error_type,
        }
