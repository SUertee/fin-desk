import json
import shlex
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.config.settings import McpSettings
from app.connectors.mcp import (
    McpInvocationError,
    McpPolicyError,
    McpResponseContractError,
    McpResponseTooLargeError,
    McpToolResponse,
    McpToolUnavailableError,
    SseMcpToolClient,
    StdioMcpToolClient,
)
from app.models.runtime import RuntimePolicyResult
from app.runtime.capabilities import CapabilityCatalog, CapabilityResolver, bind_execution_plan
from app.runtime.capabilities.contracts import CapabilityRuntimeStatus
from app.runtime.execution import AgentContext, ToolRegistry, build_execution_plan
from app.tools.mcp_market_data import (
    EXTERNAL_MARKET_HISTORY_CAPABILITY,
    VibeMarketDataTool,
    normalize_market_history,
    project_external_history_for_specialist,
)
from tests.cfo_decision_fakes import execute


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _settings(**overrides):
    return McpSettings(
        enabled=True,
        timeout_seconds=5,
        lookback_days=30,
        max_rows=30,
        **overrides,
    )


class FakeMcpClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.error:
            raise self.error
        return self.response


def _valid_response():
    return McpToolResponse(
        text=json.dumps(
            {
                "AAPL.US": {
                    "rows": 2,
                    "returned": 2,
                    "truncated": False,
                    "data": [
                        {
                            "trade_date": "2026-06-21T00:00:00",
                            "open": 95,
                            "close": 100,
                        },
                        {
                            "trade_date": "2026-07-21T00:00:00",
                            "open": 108,
                            "close": 110,
                        },
                    ],
                }
            }
        )
    )


def test_mcp_settings_reject_disallowed_command_and_missing_tool():
    with pytest.raises(ValueError, match="command is not allowlisted"):
        _settings(command="arbitrary", allowed_commands=("vibe-trading-mcp",))
    with pytest.raises(ValueError, match="tool is not allowlisted"):
        _settings(allowed_tools=("run_swarm",))
    with pytest.raises(ValueError, match="SSE URL is not allowlisted"):
        _settings(
            transport="sse",
            url="http://untrusted.example/sse",
            allowed_urls=("http://vibe-mcp:8900/sse",),
        )


@pytest.mark.asyncio
async def test_stdio_client_rejects_tool_before_starting_process():
    client = StdioMcpToolClient(
        command="vibe-trading-mcp",
        allowed_commands=("vibe-trading-mcp",),
        allowed_tools=("get_market_data",),
        timeout_seconds=5,
        max_response_bytes=100,
    )

    with pytest.raises(McpPolicyError, match="not allowlisted"):
        await client.call_tool("run_swarm", {})


@pytest.mark.asyncio
async def test_stdio_client_lists_advertised_tools(monkeypatch):
    import app.connectors.mcp.stdio_client as module

    @asynccontextmanager
    async def fake_stdio(_params):
        yield object(), object()

    class FakeSession:
        def __init__(self, *_args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(
                tools=[SimpleNamespace(name="z_tool"), SimpleNamespace(name="a_tool")]
            )

    monkeypatch.setattr(module, "stdio_client", fake_stdio)
    monkeypatch.setattr(module, "ClientSession", FakeSession)
    client = StdioMcpToolClient(
        command="vibe-trading-mcp",
        allowed_commands=("vibe-trading-mcp",),
        allowed_tools=("get_market_data",),
        timeout_seconds=5,
        max_response_bytes=100,
    )

    assert await client.list_tools() == ("a_tool", "z_tool")


@pytest.mark.asyncio
async def test_stdio_client_round_trip_with_minimal_mcp_subprocess(tmp_path):
    server_script = tmp_path / "market_mcp_server.py"
    server_script.write_text(
        """
from mcp.server.fastmcp import FastMCP

server = FastMCP("findesk-conformance")


@server.tool()
def get_market_data(symbol: str) -> dict[str, str]:
    return {"symbol": symbol, "source": "fixture"}


if __name__ == "__main__":
    server.run("stdio")
""".lstrip(),
        encoding="utf-8",
    )
    launcher = tmp_path / "market-mcp"
    launcher.write_text(
        "#!/bin/sh\n"
        f"exec {shlex.quote(sys.executable)} {shlex.quote(str(server_script))}\n",
        encoding="utf-8",
    )
    launcher.chmod(0o700)
    command = str(launcher)
    client = StdioMcpToolClient(
        command=command,
        allowed_commands=(command,),
        allowed_tools=("get_market_data",),
        timeout_seconds=10,
        max_response_bytes=1_000,
    )

    assert await client.list_tools() == ("get_market_data",)
    response = await client.call_tool("get_market_data", {"symbol": "AAPL"})
    assert "AAPL" in response.text
    assert "fixture" in response.text


@pytest.mark.asyncio
async def test_sse_client_discovers_and_calls_allowlisted_tool(monkeypatch):
    import app.connectors.mcp.sse_client as module

    @asynccontextmanager
    async def fake_sse(url):
        assert url == "http://vibe-mcp:8900/sse"
        yield object(), object()

    class FakeSession:
        def __init__(self, *_args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="get_market_data")])

        async def call_tool(self, _name, _arguments):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text='{"ok": true}')],
                structuredContent={"ok": True},
                isError=False,
            )

    monkeypatch.setattr(module, "sse_client", fake_sse)
    monkeypatch.setattr(module, "ClientSession", FakeSession)
    client = SseMcpToolClient(
        url="http://vibe-mcp:8900/sse",
        allowed_urls=("http://vibe-mcp:8900/sse",),
        allowed_tools=("get_market_data",),
        timeout_seconds=5,
        max_response_bytes=100,
    )

    assert await client.list_tools() == ("get_market_data",)
    response = await client.call_tool("get_market_data", {})
    assert response.structured_content == {"ok": True}


@pytest.mark.asyncio
async def test_stdio_client_checks_discovery_and_response_size(monkeypatch):
    import app.connectors.mcp.stdio_client as module

    @asynccontextmanager
    async def fake_stdio(_params):
        yield object(), object()

    class FakeSession:
        def __init__(self, *_args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="get_market_data")])

        async def call_tool(self, _name, _arguments):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="x" * 40)],
                structuredContent=None,
                isError=False,
            )

    monkeypatch.setattr(module, "stdio_client", fake_stdio)
    monkeypatch.setattr(module, "ClientSession", FakeSession)
    client = StdioMcpToolClient(
        command="vibe-trading-mcp",
        allowed_commands=("vibe-trading-mcp",),
        allowed_tools=("get_market_data",),
        timeout_seconds=5,
        max_response_bytes=10,
    )

    with pytest.raises(McpResponseTooLargeError):
        await client.call_tool("get_market_data", {})


@pytest.mark.asyncio
async def test_stdio_client_rejects_tool_not_advertised(monkeypatch):
    import app.connectors.mcp.stdio_client as module

    @asynccontextmanager
    async def fake_stdio(_params):
        yield object(), object()

    class FakeSession:
        def __init__(self, *_args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[])

    monkeypatch.setattr(module, "stdio_client", fake_stdio)
    monkeypatch.setattr(module, "ClientSession", FakeSession)
    client = StdioMcpToolClient(
        command="vibe-trading-mcp",
        allowed_commands=("vibe-trading-mcp",),
        allowed_tools=("get_market_data",),
        timeout_seconds=5,
        max_response_bytes=100,
    )

    with pytest.raises(McpToolUnavailableError):
        await client.call_tool("get_market_data", {})


def test_market_history_normalization_is_bounded_and_typed():
    artifact = normalize_market_history(
        _valid_response(),
        symbol="AAPL",
        provider_symbol="AAPL.US",
        asset_type="equity",
        date_from=NOW.date().replace(month=6),
        date_to=NOW.date(),
        source_requested="yfinance",
        max_rows=30,
        fetched_at=NOW,
    )
    payload = artifact.model_dump(mode="json")

    assert artifact.status == "available"
    assert artifact.bar_count == 2
    assert str(artifact.period_return_percent) == "10.00"
    assert artifact.latest_as_of == "2026-07-21T00:00:00"
    assert artifact.trade_actions_allowed is False
    assert "Open" not in json.dumps(payload)
    projected = project_external_history_for_specialist(artifact)
    assert projected["history"]["bar_count"] == 2
    assert projected["quote"]["price"] == {"amount": "110", "currency": "USD"}


def test_market_history_rejects_invalid_json_and_excess_rows():
    kwargs = dict(
        symbol="AAPL",
        provider_symbol="AAPL.US",
        asset_type="equity",
        date_from=NOW.date().replace(month=6),
        date_to=NOW.date(),
        source_requested="yfinance",
        max_rows=1,
        fetched_at=NOW,
    )
    with pytest.raises(McpResponseContractError, match="valid JSON"):
        normalize_market_history(McpToolResponse(text="not-json"), **kwargs)
    with pytest.raises(McpResponseContractError, match="row limit"):
        normalize_market_history(_valid_response(), **kwargs)


@pytest.mark.asyncio
async def test_vibe_tool_calls_one_bounded_read_only_tool():
    client = FakeMcpClient(response=_valid_response())
    tool = VibeMarketDataTool(client, _settings(), clock=lambda: NOW)
    observation = await tool.execute(
        {
            "agent": "cfo",
            "context": AgentContext(
                request_id="req-mcp",
                user_id="demo",
                entrypoint="chat",
                raw_message="请用 Vibe MCP 查询股票 AAPL 的外部行情",
                effective_message="请用 Vibe MCP 查询股票 AAPL 的外部行情",
            ),
        }
    )

    assert observation.success is True
    assert observation.result["schema_version"] == "external-market-history/v1"
    assert client.calls[0][0] == "get_market_data"
    assert client.calls[0][1] == {
        "codes": ["AAPL.US"],
        "start_date": "2026-06-21",
        "end_date": "2026-07-21",
        "source": "yfinance",
        "interval": "1D",
        "max_rows": 30,
    }


@pytest.mark.asyncio
async def test_vibe_tool_failure_is_explicit_and_has_no_fallback():
    client = FakeMcpClient(error=McpInvocationError("provider failed"))
    observation = await VibeMarketDataTool(
        client, _settings(), clock=lambda: NOW
    ).execute(
        {
            "agent": "cfo",
            "context": AgentContext(
                request_id="req-mcp-fail",
                user_id="demo",
                entrypoint="chat",
                raw_message="请用 Vibe MCP 查询股票 AAPL 的外部行情",
                effective_message="请用 Vibe MCP 查询股票 AAPL 的外部行情",
            ),
        }
    )

    assert observation.success is False
    assert observation.error_class == "McpInvocationError"
    assert client.calls == [
        (
            "get_market_data",
            {
                "codes": ["AAPL.US"],
                "start_date": "2026-06-21",
                "end_date": "2026-07-21",
                "source": "yfinance",
                "interval": "1D",
                "max_rows": 30,
            },
        )
    ]


def test_planner_selects_external_or_internal_market_evidence_exclusively():
    from app.runtime.orchestration.finance_runtime import FinanceRuntime

    policy = RuntimePolicyResult(
        complexity="complex",
        risk_level="high",
        required_specialists=["investment_research"],
        audit_required=True,
        max_tool_calls=10,
    )
    tool = VibeMarketDataTool(
        FakeMcpClient(response=_valid_response()), _settings(), clock=lambda: NOW
    )
    runtime = FinanceRuntime(mcp_market_data_tool=tool)
    external = build_execution_plan(
        [EXTERNAL_MARKET_HISTORY_CAPABILITY, "investment.research_review"],
        policy,
        runtime.capability_catalog,
    )
    internal = build_execution_plan(
        ["investment.research_review"], policy, runtime.capability_catalog
    )

    assert EXTERNAL_MARKET_HISTORY_CAPABILITY in external.tool_capability_ids
    assert "investment.research_context" not in external.tool_capability_ids
    assert "investment.research_context" in internal.tool_capability_ids


def test_mcp_tool_binds_through_capability_catalog():
    tool = VibeMarketDataTool(
        FakeMcpClient(response=_valid_response()), _settings(), clock=lambda: NOW
    )
    catalog = CapabilityCatalog.from_registries(
        ToolRegistry([tool.spec()]),
        {},
    )
    item = catalog.list()[0]
    plan = build_execution_plan(
        [EXTERNAL_MARKET_HISTORY_CAPABILITY],
        RuntimePolicyResult(
            required_specialists=["investment_research"],
            max_tool_calls=10,
        ),
        catalog,
    )
    external_only = type(plan)(
        steps=[
            step
            for step in plan.steps
            if step.capability_id == EXTERNAL_MARKET_HISTORY_CAPABILITY
        ]
    )
    bound = bind_execution_plan(
        external_only,
        CapabilityResolver(catalog),
        granted_capabilities={EXTERNAL_MARKET_HISTORY_CAPABILITY},
    )

    assert item.descriptor.source == "mcp"
    assert bound.tool_names == ["get_vibe_market_data"]


@pytest.mark.asyncio
async def test_runtime_uses_mcp_artifact_without_internal_provider_fallback(monkeypatch):
    from app.runtime.orchestration import finance_runtime
    from app.runtime.orchestration.finance_runtime import FinanceRuntime

    records = []
    client = FakeMcpClient(response=_valid_response())
    tool = VibeMarketDataTool(client, _settings(), clock=lambda: NOW)
    monkeypatch.setattr(
        finance_runtime, "list_latest_quality_reports_db", lambda _user_id: []
    )
    monkeypatch.setattr(finance_runtime, "write_session_context", lambda **_kwargs: None)
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: records.append(record) or True,
    )
    runtime = FinanceRuntime(
        mcp_market_data_tool=tool,
        decision_engine=execute(
            EXTERNAL_MARKET_HISTORY_CAPABILITY,
            "investment.research_review",
        ),
    )
    runtime.llm_client = None

    result = await runtime.handle(
        user_id="demo",
        message="请用 Vibe MCP 查询股票 AAPL 的外部行情",
        profile={"name": "Demo", "preferences": {"preferred_language": "zh"}},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    called = {call.name for call in records[0].tool_calls if call.status == "called"}
    assert result["execution"]["outcome"] == "executed"
    assert "get_vibe_market_data" in called
    assert "get_investment_research_context" not in called
    assert result["data"]["summary_cards"][0]["value"] == "USD 110"
    assert client.calls[0][0] == "get_market_data"


@pytest.mark.asyncio
async def test_runtime_mcp_failure_remains_external_and_reports_unavailable(monkeypatch):
    from app.runtime.orchestration import finance_runtime
    from app.runtime.orchestration.finance_runtime import FinanceRuntime

    records = []
    client = FakeMcpClient(error=McpInvocationError("provider failed"))
    tool = VibeMarketDataTool(client, _settings(), clock=lambda: NOW)
    monkeypatch.setattr(
        finance_runtime, "list_latest_quality_reports_db", lambda _user_id: []
    )
    monkeypatch.setattr(finance_runtime, "write_session_context", lambda **_kwargs: None)
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: records.append(record) or True,
    )
    runtime = FinanceRuntime(
        mcp_market_data_tool=tool,
        decision_engine=execute(
            EXTERNAL_MARKET_HISTORY_CAPABILITY,
            "investment.research_review",
        ),
    )
    runtime.llm_client = None

    result = await runtime.handle(
        user_id="demo",
        message="请用 Vibe MCP 查询股票 AAPL 的外部行情",
        profile={"name": "Demo", "preferences": {"preferred_language": "zh"}},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    calls = {call.name: call.status for call in records[0].tool_calls}
    assert calls["get_vibe_market_data"] == "failed"
    assert "get_investment_research_context" not in calls
    assert "还不能完成" in result["reply"]


@pytest.mark.asyncio
async def test_runtime_does_not_plan_unhealthy_external_capability(monkeypatch):
    from app.runtime.orchestration import finance_runtime
    from app.runtime.orchestration.finance_runtime import FinanceRuntime

    class FakeHealth:
        def __init__(self):
            self.calls = 0

        async def vibe_market_data_status(self):
            self.calls += 1
            return CapabilityRuntimeStatus(
                available=False,
                reason="MCP discovery failed: McpInvocationError",
            )

    records = []
    client = FakeMcpClient(response=_valid_response())
    health = FakeHealth()
    tool = VibeMarketDataTool(client, _settings(), clock=lambda: NOW)
    monkeypatch.setattr(
        finance_runtime, "list_latest_quality_reports_db", lambda _user_id: []
    )
    monkeypatch.setattr(finance_runtime, "write_session_context", lambda **_kwargs: None)
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: records.append(record) or True,
    )
    runtime = FinanceRuntime(
        mcp_market_data_tool=tool,
        capability_health_service=health,
        decision_engine=execute(
            EXTERNAL_MARKET_HISTORY_CAPABILITY,
            "investment.research_review",
        ),
    )
    runtime.llm_client = None

    result = await runtime.handle(
        user_id="demo",
        message="请用 Vibe MCP 查询股票 AAPL 的外部行情",
        profile={"name": "Demo", "preferences": {"preferred_language": "zh"}},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    called = {call.name for call in records[0].tool_calls if call.status == "called"}
    assert health.calls == 1
    assert client.calls == []
    assert "get_vibe_market_data" not in called
    assert "get_investment_research_context" not in called
    assert result["execution"]["outcome"] == "blocked"
