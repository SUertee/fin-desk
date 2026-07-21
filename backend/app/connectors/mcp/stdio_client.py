"""Allowlisted stdio client for the stable MCP Python SDK."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.connectors.mcp.contracts import (
    McpInvocationError,
    McpPolicyError,
    McpResponseTooLargeError,
    McpToolResponse,
    McpToolUnavailableError,
)


class StdioMcpToolClient:
    def __init__(
        self,
        *,
        command: str,
        allowed_commands: tuple[str, ...],
        allowed_tools: tuple[str, ...],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> None:
        if command not in allowed_commands:
            raise McpPolicyError("MCP stdio command is not allowlisted")
        self.command = command
        self.allowed_tools = frozenset(allowed_tools)
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> McpToolResponse:
        if name not in self.allowed_tools:
            raise McpPolicyError(f"MCP tool is not allowlisted: {name}")

        params = StdioServerParameters(command=self.command, args=[])
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
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

        text_parts = [
            str(item.text)
            for item in result.content
            if getattr(item, "type", "") == "text" and getattr(item, "text", None)
        ]
        text = "\n".join(text_parts)
        structured = getattr(result, "structuredContent", None)
        serialized = json.dumps(
            structured if structured is not None else text,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        if len(serialized) > self.max_response_bytes:
            raise McpResponseTooLargeError("MCP response exceeds configured bound")
        if result.isError:
            raise McpInvocationError("MCP tool returned an error result")
        return McpToolResponse(text=text, structured_content=structured)
