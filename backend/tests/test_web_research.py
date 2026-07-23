from datetime import datetime, timezone

import pytest

from app.config.settings import WebResearchSettings
from app.connectors.web_search.errors import WebSearchBudgetExceeded
from app.models.runtime import RuntimePolicyResult
from app.models.web_research import (
    WebResearchRequest,
    WebSearchProviderItem,
    WebSearchProviderResult,
    WebSearchProviderStatus,
)
from app.runtime.execution.planner import build_execution_plan
from app.services.web_research import WebResearchBudget, WebResearchService
from tests.cfo_decision_fakes import direct, execute


NOW = datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self, *, available=True):
        self.available = available
        self.calls = 0

    def get_status(self):
        return WebSearchProviderStatus(
            availability="available" if self.available else "unavailable",
            configured_provider="fake",
            allowed=True,
            detail=None if self.available else "fake provider is not configured",
        )

    def search(self, query, *, domains, max_results, topic, fetched_at):
        self.calls += 1
        return WebSearchProviderResult(
            provider="fake",
            query=query,
            fetched_at=fetched_at,
            items=[
                WebSearchProviderItem(
                    title="Official guidance",
                    url="https://policy.example.gov/guidance",
                    snippet="Reviewed source material.",
                    published_at=NOW,
                    score=0.9,
                ),
                WebSearchProviderItem(
                    title="Unapproved blog",
                    url="https://blog.example.com/post",
                    snippet="Must be filtered.",
                    score=0.8,
                ),
            ],
        )


def _service(provider=None):
    cache = {}

    def read(key, *, now):
        entry = cache.get(key)
        return entry if entry and entry.expires_at > now else None

    def write(entry):
        cache[entry.cache_key] = entry
        return True

    settings = WebResearchSettings(
        provider="fake",
        allowed_providers=("fake",),
        allowed_domains=("example.gov",),
        max_results=5,
        outbound_call_budget=2,
    )
    return WebResearchService(
        provider or FakeProvider(),
        settings=settings,
        cache_reader=read,
        cache_writer=write,
        clock=lambda: NOW,
    )


def test_search_filters_domains_and_cache_hit_consumes_no_budget():
    provider = FakeProvider()
    service = _service(provider)

    first_budget = service.new_budget()
    first = service.search(
        WebResearchRequest(query="official policy"), budget=first_budget
    )
    second_budget = service.new_budget()
    second = service.search(
        WebResearchRequest(query="official policy"), budget=second_budget
    )

    assert provider.calls == 1
    assert [item.domain for item in first.items] == ["policy.example.gov"]
    assert first.excluded_count == 1
    assert first.external_calls.used == 1
    assert second.cache.cache_hit is True
    assert second.external_calls.used == 0


def test_unconfigured_provider_returns_typed_unavailable():
    service = _service(FakeProvider(available=False))
    result = service.search(
        WebResearchRequest(query="rates"), budget=service.new_budget()
    )

    assert result.status == "unavailable"
    assert result.items == []
    assert "not configured" in result.limitations[0]


def test_requested_domain_must_be_allowlisted():
    service = _service()
    with pytest.raises(ValueError, match="not allowlisted"):
        service.search(
            WebResearchRequest(query="policy", domains=["example.com"]),
            budget=service.new_budget(),
        )


def test_exhausted_budget_blocks_provider_call():
    service = _service()
    with pytest.raises(WebSearchBudgetExceeded):
        service.search(
            WebResearchRequest(query="policy"),
            budget=WebResearchBudget(limit=1, used=1),
        )


def test_market_plan_searches_before_specialist_handoff():
    from app.runtime.orchestration.factory import build_finance_runtime

    runtime = build_finance_runtime()
    policy = RuntimePolicyResult(
        complexity="moderate",
        risk_level="medium",
        required_specialists=["market_context"],
        audit_required=True,
        allow_market_context=True,
        max_tool_calls=6,
    )
    plan = build_execution_plan(
        ["market.context_review"], policy, runtime.capability_catalog
    )
    tool_index = next(
        index
        for index, step in enumerate(plan.steps)
        if step.capability_id == "market.web_research"
    )
    handoff_index = next(
        index
        for index, step in enumerate(plan.steps)
        if step.step_type == "handoff" and step.capability_id == "market.context_review"
    )

    assert tool_index < handoff_index


@pytest.mark.asyncio
async def test_runtime_injects_research_before_market_specialist(monkeypatch):
    from app.runtime.orchestration import finance_runtime
    from app.runtime.orchestration.factory import build_finance_runtime

    records = []
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: records.append(record) or True,
    )
    runtime = build_finance_runtime(
        web_research_service=_service(),
        decision_engine=execute("market.context_review"),
        llm_client=None,
    )

    result = await runtime.handle(
        user_id="demo",
        message="How does the latest market news affect my budget?",
        profile={"name": "Demo"},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    trace = records[0]
    calls = {call.name: call.status for call in trace.tool_calls}
    market_handoff = next(
        handoff for handoff in trace.handoffs if handoff.to_agent == "market_context"
    )
    assert result["agent_used"] == "cfo"
    assert calls["search_web_research"] == "called"
    assert market_handoff.output["findings"][0]["source_url"] == (
        "https://policy.example.gov/guidance"
    )


@pytest.mark.asyncio
async def test_light_conversation_never_calls_web_research(monkeypatch):
    from app.runtime.orchestration import finance_runtime
    from app.runtime.orchestration.factory import build_finance_runtime

    provider = FakeProvider()
    records = []
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: records.append(record) or True,
    )
    runtime = build_finance_runtime(
        web_research_service=_service(provider),
        decision_engine=direct("你好，我在。"),
        llm_client=None,
    )

    result = await runtime.handle(
        user_id="demo",
        message="你好",
        profile={"name": "Demo"},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    assert result["execution"]["outcome"] == "direct_response"
    assert provider.calls == 0
    assert all(call.name != "search_web_research" for call in records[0].tool_calls)


@pytest.mark.asyncio
async def test_direct_cfo_reply_does_not_call_external_search(monkeypatch):
    from app.runtime.execution import finance_toolset
    from app.runtime.orchestration import finance_runtime
    from app.runtime.orchestration.factory import build_finance_runtime

    provider = FakeProvider()
    records = []
    monkeypatch.setattr(
        finance_toolset, "list_latest_quality_reports_db", lambda _user: []
    )
    monkeypatch.setattr(
        finance_runtime, "write_session_context", lambda **_kwargs: None
    )
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: records.append(record) or True,
    )
    runtime = build_finance_runtime(
        web_research_service=_service(provider),
        decision_engine=direct(
            "I can run sourced market research when the question requires it."
        ),
        llm_client=None,
    )

    await runtime.handle(
        user_id="demo",
        message="What is the latest market news?",
        profile={"name": "Demo"},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    assert provider.calls == 0
    assert "market_context" not in records[0].selected_agents
    assert all(call.name != "search_web_research" for call in records[0].tool_calls)
