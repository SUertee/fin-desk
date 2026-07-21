"""Short-lived health projection for optional external capabilities."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from time import monotonic
from typing import Callable

from app.config.settings import McpSettings, get_settings
from app.connectors.mcp import McpClientError, McpToolClient, build_mcp_client
from app.runtime.capabilities.contracts import CapabilityRuntimeStatus


class CapabilityHealthService:
    def __init__(
        self,
        settings: McpSettings,
        *,
        client: McpToolClient | None = None,
        clock: Callable[[], float] = monotonic,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.clock = clock
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._cached: CapabilityRuntimeStatus | None = None
        self._expires_at = 0.0

    async def vibe_market_data_status(
        self, *, force: bool = False
    ) -> CapabilityRuntimeStatus:
        checked_at = self.now()
        if not self.settings.enabled:
            return CapabilityRuntimeStatus(
                enabled=False,
                available=False,
                reason="Disabled by configuration",
                checked_at=checked_at,
            )
        current = self.clock()
        if not force and self._cached is not None and current < self._expires_at:
            return self._cached
        try:
            tools = await (self.client or build_mcp_client(self.settings)).list_tools()
            if "get_market_data" not in tools:
                status = CapabilityRuntimeStatus(
                    available=False,
                    reason="Required MCP tool is not advertised",
                    checked_at=checked_at,
                )
            else:
                status = CapabilityRuntimeStatus(checked_at=checked_at)
        except (McpClientError, ValueError, RuntimeError) as exc:
            status = CapabilityRuntimeStatus(
                available=False,
                reason=f"MCP discovery failed: {type(exc).__name__}",
                checked_at=checked_at,
            )
        self._cached = status
        self._expires_at = current + self.settings.health_ttl_seconds
        return status


@lru_cache(maxsize=1)
def get_capability_health_service() -> CapabilityHealthService:
    return CapabilityHealthService(get_settings().mcp)
