from types import SimpleNamespace

from app.config.settings import McpSettings
from app.runtime.orchestration import factory
from app.runtime.response.finance_response_builder import FinanceResponseBuilder
from tests.cfo_decision_fakes import direct


def test_factory_builds_default_runtime_without_network_calls(monkeypatch):
    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: SimpleNamespace(mcp=McpSettings(enabled=False)),
    )

    runtime = factory.build_finance_runtime(llm_client=None)

    assert runtime.tool_registry.get("get_finance_context") is not None
    assert runtime.capability_catalog.get("finance.context") is not None


def test_factory_projects_disabled_optional_mcp_provider(monkeypatch):
    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: SimpleNamespace(mcp=McpSettings(enabled=False)),
    )
    monkeypatch.setattr(
        factory,
        "build_vibe_market_data_tool",
        lambda _settings: (_ for _ in ()).throw(
            AssertionError("disabled MCP must not be constructed")
        ),
    )

    runtime = factory.build_finance_runtime(llm_client=None)
    entry = runtime.capability_catalog.get(
        "investment.external_market_history"
    )

    assert entry is not None
    assert entry.status.enabled is False
    assert entry.status.available is False


def test_factory_uses_injected_collaborators():
    builder = FinanceResponseBuilder()
    decision_engine = direct("Injected")

    runtime = factory.build_finance_runtime(
        llm_client=None,
        response_builder=builder,
        decision_engine=decision_engine,
    )

    assert runtime.response_builder is builder
    assert runtime.decision_engine is decision_engine
