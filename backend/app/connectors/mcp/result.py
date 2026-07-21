"""Bounded projection of MCP SDK tool results."""

from __future__ import annotations

import json
from typing import Any

from app.connectors.mcp.contracts import (
    McpInvocationError,
    McpResponseTooLargeError,
    McpToolResponse,
)


def project_tool_result(result: Any, *, max_response_bytes: int) -> McpToolResponse:
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
    if len(serialized) > max_response_bytes:
        raise McpResponseTooLargeError("MCP response exceeds configured bound")
    if result.isError:
        raise McpInvocationError("MCP tool returned an error result")
    return McpToolResponse(text=text, structured_content=structured)
