"""Bounded tool contracts and executor for self-hosted agent execution."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


ToolExecutor = Callable[[dict[str, Any]], "ToolObservation | Awaitable[ToolObservation]"]
ToolPolicy = Callable[["ToolSpec"], bool]


@dataclass(frozen=True)
class ToolObservation:
    """A structured fact returned by a deterministic tool."""

    tool_name: str
    success: bool
    agent: str
    purpose: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error_class: str = ""
    error_message: str = ""
    latency_ms: float | None = None
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    executor: ToolExecutor
    owner: str = "finance"
    deterministic: bool = True
    model_visible: bool = True


class ToolRegistry:
    """Process-local tool directory with per-run filtering."""

    def __init__(self, specs: list[ToolSpec] | None = None):
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def available(self, policy: ToolPolicy | None = None) -> list[ToolSpec]:
        if policy is None:
            return list(self._specs.values())
        return [spec for spec in self._specs.values() if policy(spec)]

    async def execute(self, name: str, payload: dict[str, Any]) -> ToolObservation:
        spec = self.get(name)
        if spec is None:
            return ToolObservation(
                tool_name=name,
                success=False,
                agent="runtime",
                error_class="unknown_tool",
                error_message=f"Unknown tool: {name}",
            )
        result = spec.executor(payload)
        if inspect.isawaitable(result):
            return await result
        return result


class BoundedToolExecutor:
    """Executes registered tools with max-call and allow-list constraints."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        allowed_tools: list[str] | None = None,
        max_tool_calls: int = 6,
    ):
        self.registry = registry
        self.allowed_tools = set(allowed_tools or [])
        self.max_tool_calls = max(0, max_tool_calls)
        self.calls_made = 0

    async def execute(self, name: str, payload: dict[str, Any]) -> ToolObservation:
        if self.allowed_tools and name not in self.allowed_tools:
            return ToolObservation(
                tool_name=name,
                success=False,
                agent=str(payload.get("agent") or "runtime"),
                error_class="tool_not_allowed",
                error_message=f"Tool is not allowed by runtime policy: {name}",
            )
        if self.calls_made >= self.max_tool_calls:
            return ToolObservation(
                tool_name=name,
                success=False,
                agent=str(payload.get("agent") or "runtime"),
                error_class="tool_budget_exceeded",
                error_message="Runtime tool call budget exceeded",
            )
        self.calls_made += 1
        return await self.registry.execute(name, payload)
