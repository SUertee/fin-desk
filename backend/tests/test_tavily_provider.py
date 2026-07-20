from datetime import datetime, timezone
import json

import httpx
import pytest

from app.connectors.web_search.errors import (
    WebSearchNotConfigured,
    WebSearchProviderError,
)
from app.connectors.web_search.tavily_provider import TavilyWebSearchProvider


NOW = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


def _provider(handler, *, api_key="test-key", allowed=True):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return TavilyWebSearchProvider(
        api_key=api_key,
        base_url="https://tavily.test",
        allowed=allowed,
        client=client,
    )


def test_tavily_normalizes_results_and_request_scope():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url == "https://tavily.test/search"
        assert payload["include_domains"] == ["federalreserve.gov"]
        assert payload["include_answer"] is False
        assert payload["include_raw_content"] is False
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Rate decision",
                        "url": "https://federalreserve.gov/release",
                        "content": "Official statement",
                        "published_date": "2026-07-19T10:00:00Z",
                        "score": 0.95,
                    }
                ]
            },
        )

    result = _provider(handler).search(
        "latest rate decision",
        domains=["federalreserve.gov"],
        max_results=3,
        topic="news",
        fetched_at=NOW,
    )

    assert result.provider == "tavily"
    assert result.items[0].title == "Rate decision"
    assert result.items[0].published_at == datetime(
        2026, 7, 19, 10, 0, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    ("api_key", "allowed", "expected"),
    [("", True, "not configured"), ("test-key", False, "not allowlisted")],
)
def test_tavily_refuses_unavailable_configuration(api_key, allowed, expected):
    provider = _provider(
        lambda _request: httpx.Response(500), api_key=api_key, allowed=allowed
    )

    with pytest.raises(WebSearchNotConfigured, match=expected):
        provider.search(
            "rates",
            domains=[],
            max_results=3,
            topic="news",
            fetched_at=NOW,
        )


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"detail": "rate limited"}),
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"answer": "missing results"}),
    ],
)
def test_tavily_maps_http_and_contract_failures(response):
    provider = _provider(lambda _request: response)

    with pytest.raises(WebSearchProviderError, match="Tavily"):
        provider.search(
            "rates",
            domains=[],
            max_results=3,
            topic="news",
            fetched_at=NOW,
        )


def test_tavily_skips_malformed_items_without_fabricating():
    provider = _provider(
        lambda _request: httpx.Response(
            200,
            json={
                "results": [
                    {"title": "", "url": "not-a-url"},
                    "unexpected",
                ]
            },
        )
    )

    result = provider.search(
        "rates",
        domains=[],
        max_results=3,
        topic="news",
        fetched_at=NOW,
    )

    assert result.items == []
