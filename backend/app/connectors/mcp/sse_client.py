"""Allowlisted SSE client for a separately deployed MCP server."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

from app.connectors.mcp.contracts import (
    McpInvocationError,
    McpPolicyError,
    McpToolResponse,
    McpToolUnavailableError,
)
from app.connectors.mcp.result import project_tool_result


class SseMcpToolClient:
    def __init__(
        self,
        *,
        url: str,
        allowed_urls: tuple[str, ...],
        allowed_tools: tuple[str, ...],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> None:
        if url not in allowed_urls:
            raise McpPolicyError("MCP SSE URL is not allowlisted")
        self.url = url
        self.allowed_tools = frozenset(allowed_tools)
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    async def list_tools(self) -> tuple[str, ...]:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with self._session() as session:
                    listed = await session.list_tools()
                    return tuple(sorted(tool.name for tool in listed.tools))
        except TimeoutError as exc:
            raise McpInvocationError("MCP discovery timed out") from exc
        except Exception as exc:
            raise McpInvocationError(
                f"MCP discovery failed: {type(exc).__name__}"
            ) from exc

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> McpToolResponse:
        if name not in self.allowed_tools:
            raise McpPolicyError(f"MCP tool is not allowlisted: {name}")
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with self._session() as session:
                    listed = await session.list_tools()
                    advertised = {tool.name for tool in listed.tools}
                    if name not in advertised:
                        raise McpToolUnavailableError(
                            f"MCP server does not advertise tool: {name}"
                        )
                    result = await session.call_tool(name, arguments)
        except McpToolUnavailableError:
            raise
        except TimeoutError as exc:
            raise McpInvocationError("MCP tool call timed out") from exc
        except Exception as exc:
            raise McpInvocationError(
                f"MCP tool call failed: {type(exc).__name__}"
            ) from exc
        return project_tool_result(result, max_response_bytes=self.max_response_bytes)

    def _session(self):
        return _SseSession(self.url)


class _SseSession:
    def __init__(self, url: str) -> None:
        self.url = url
        self._transport = None
        self._session = None

    async def __aenter__(self):
        self._transport = sse_client(self.url)
        read_stream, write_stream = await self._transport.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        session = await self._session.__aenter__()
        await session.initialize()
        return session

    async def __aexit__(self, exc_type, exc, tb):
        if self._session is not None:
            await self._session.__aexit__(exc_type, exc, tb)
        if self._transport is not None:
            await self._transport.__aexit__(exc_type, exc, tb)
