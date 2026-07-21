"""Transport-neutral contracts for allowlisted MCP tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class McpClientError(RuntimeError):
    pass


class McpPolicyError(McpClientError):
    pass


class McpToolUnavailableError(McpClientError):
    pass


class McpInvocationError(McpClientError):
    pass


class McpResponseTooLargeError(McpClientError):
    pass


class McpResponseContractError(McpClientError):
    pass


@dataclass(frozen=True)
class McpToolResponse:
    text: str = ""
    structured_content: dict[str, Any] | None = None


class McpToolClient(Protocol):
    async def list_tools(self) -> tuple[str, ...]: ...

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> McpToolResponse: ...
