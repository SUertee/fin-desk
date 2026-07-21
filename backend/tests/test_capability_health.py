from datetime import datetime, timezone

import pytest

from app.config.settings import McpSettings
from app.connectors.mcp import McpInvocationError
from app.runtime.capabilities.health import CapabilityHealthService


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, tools=(), error=None):
        self.tools = tuple(tools)
        self.error = error
        self.calls = 0

    async def list_tools(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.tools

    async def call_tool(self, _name, _arguments):
        raise AssertionError("Health must not invoke a business tool")


def _settings(**overrides):
    enabled = overrides.pop("enabled", True)
    return McpSettings(
        enabled=enabled,
        health_ttl_seconds=30,
        **overrides,
    )


@pytest.mark.asyncio
async def test_disabled_capability_does_not_create_or_call_client():
    client = FakeClient(("get_market_data",))
    service = CapabilityHealthService(
        _settings(enabled=False), client=client, now=lambda: NOW
    )

    status = await service.vibe_market_data_status()

    assert status.enabled is False
    assert status.available is False
    assert status.checked_at == NOW
    assert client.calls == 0


@pytest.mark.asyncio
async def test_discovery_health_is_cached_until_ttl_expires():
    ticks = iter((0.0, 10.0, 31.0))
    client = FakeClient(("get_market_data",))
    service = CapabilityHealthService(
        _settings(), client=client, clock=lambda: next(ticks), now=lambda: NOW
    )

    first = await service.vibe_market_data_status()
    cached = await service.vibe_market_data_status()
    refreshed = await service.vibe_market_data_status()

    assert first.available and cached.available and refreshed.available
    assert client.calls == 2


@pytest.mark.asyncio
async def test_missing_tool_and_transport_failure_are_unhealthy():
    missing = CapabilityHealthService(
        _settings(), client=FakeClient(("other_tool",)), now=lambda: NOW
    )
    failed = CapabilityHealthService(
        _settings(),
        client=FakeClient(error=McpInvocationError("offline")),
        now=lambda: NOW,
    )

    missing_status = await missing.vibe_market_data_status()
    failed_status = await failed.vibe_market_data_status()

    assert missing_status.available is False
    assert missing_status.reason == "Required MCP tool is not advertised"
    assert failed_status.available is False
    assert failed_status.reason == "MCP discovery failed: McpInvocationError"
