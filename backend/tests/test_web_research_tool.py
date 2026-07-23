from datetime import datetime, timezone

import pytest

from app.config.settings import WebResearchSettings
from app.models.web_research import (
    WebSearchProviderItem,
    WebSearchProviderResult,
    WebSearchProviderStatus,
)
from app.runtime.execution.context import AgentContext
from app.services.web_research import WebResearchService
from app.tools.web_research import WebResearchTool, sanitize_web_research_query


NOW = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


class CapturingProvider:
    def __init__(self, *, available: bool = True):
        self.available = available
        self.queries: list[str] = []

    def get_status(self):
        return WebSearchProviderStatus(
            availability="available" if self.available else "unavailable",
            configured_provider="fake",
            allowed=True,
            detail=None if self.available else "provider unavailable",
        )

    def search(self, query, *, domains, max_results, topic, fetched_at):
        self.queries.append(query)
        return WebSearchProviderResult(
            provider="fake",
            query=query,
            fetched_at=fetched_at,
            items=[
                WebSearchProviderItem(
                    title="Central bank release",
                    url="https://policy.example.gov/rates",
                    snippet="Official current-rate context.",
                    published_at=NOW,
                    score=0.9,
                )
            ],
        )


def _tool(provider=None) -> WebResearchTool:
    settings = WebResearchSettings(
        provider="fake",
        allowed_providers=("fake",),
        allowed_domains=("example.gov",),
        max_results=3,
        outbound_call_budget=1,
    )
    service = WebResearchService(
        provider or CapturingProvider(),
        settings=settings,
        cache_reader=lambda *_args, **_kwargs: None,
        cache_writer=lambda _entry: True,
        clock=lambda: NOW,
    )
    return WebResearchTool(service)


def _context(message: str) -> AgentContext:
    return AgentContext(
        request_id="req-web",
        user_id="demo",
        entrypoint="chat",
        raw_message=message,
        effective_message=message,
        profile={"name": "Ryan", "email": "ryan@example.com"},
    )


def test_query_sanitization_removes_profile_and_obvious_identifiers():
    query = sanitize_web_research_query(
        "Ryan ryan@example.com account 6222021234567890 latest rate news",
        profile={"name": "Ryan", "email": "ryan@example.com"},
    )

    assert "Ryan" not in query
    assert "ryan@example.com" not in query
    assert "6222021234567890" not in query
    assert "latest rate news" in query


def test_query_sanitization_is_bounded():
    query = sanitize_web_research_query("market " * 100)

    assert len(query) == 240


@pytest.mark.asyncio
async def test_tool_returns_structured_evidence_and_uses_shared_budget():
    provider = CapturingProvider()
    tool = _tool(provider)
    budget = tool.new_budget()
    payload = {
        "agent": "cfo",
        "context": _context("Ryan asks about latest market news 6222021234567890"),
        "web_research_budget": budget,
    }

    first = await tool.execute(payload)
    second = await tool.execute(
        {
            **payload,
            "context": _context("What changed in the latest rate decision?"),
        }
    )

    assert first.success is True
    assert first.result["status"] == "available"
    assert first.evidence_refs == ["https://policy.example.gov/rates"]
    assert budget.used == 1
    assert len(provider.queries) == 1
    assert "Ryan" not in provider.queries[0]
    assert "6222021234567890" not in provider.queries[0]
    assert second.success is False
    assert second.error_class == "external_call_budget_exceeded"


@pytest.mark.asyncio
async def test_provider_unavailable_remains_typed_evidence():
    tool = _tool(CapturingProvider(available=False))

    observation = await tool.execute(
        {
            "agent": "cfo",
            "context": _context("latest market news"),
            "web_research_budget": tool.new_budget(),
        }
    )

    assert observation.success is True
    assert observation.result["status"] == "unavailable"
    assert observation.result["external_calls"]["used"] == 0


@pytest.mark.asyncio
async def test_tool_requires_run_scoped_budget():
    tool = _tool()

    observation = await tool.execute(
        {"agent": "cfo", "context": _context("latest market news")}
    )

    assert observation.success is False
    assert observation.error_class == "missing_run_budget"
