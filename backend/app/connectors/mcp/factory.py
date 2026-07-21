"""Build the configured MCP transport without implicit fallback."""

from app.config.settings import McpSettings
from app.connectors.mcp.contracts import McpToolClient
from app.connectors.mcp.sse_client import SseMcpToolClient
from app.connectors.mcp.stdio_client import StdioMcpToolClient


def build_mcp_client(settings: McpSettings) -> McpToolClient:
    common = {
        "allowed_tools": settings.allowed_tools,
        "timeout_seconds": settings.timeout_seconds,
        "max_response_bytes": settings.max_response_bytes,
    }
    if settings.transport == "sse":
        return SseMcpToolClient(
            url=settings.url,
            allowed_urls=settings.allowed_urls,
            **common,
        )
    return StdioMcpToolClient(
        command=settings.command,
        allowed_commands=settings.allowed_commands,
        **common,
    )
