"""Tavily implementation of the provider-neutral search contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.connectors.web_search.errors import (
    WebSearchNotConfigured,
    WebSearchProviderError,
)
from app.models.web_research import (
    WebSearchProviderItem,
    WebSearchProviderResult,
    WebSearchProviderStatus,
)


def _provider_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class TavilyWebSearchProvider:
    name = "tavily"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.tavily.com",
        timeout_seconds: int = 10,
        allowed: bool = True,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.allowed = allowed
        self.client = client

    def get_status(self) -> WebSearchProviderStatus:
        if not self.allowed:
            return WebSearchProviderStatus(
                availability="unavailable",
                configured_provider=self.name,
                allowed=False,
                detail="web-search provider is not allowlisted",
            )
        if not self.api_key:
            return WebSearchProviderStatus(
                availability="unavailable",
                configured_provider=self.name,
                allowed=True,
                detail="TAVILY_API_KEY is not configured",
            )
        return WebSearchProviderStatus(
            availability="available",
            configured_provider=self.name,
            allowed=True,
        )

    def search(
        self,
        query: str,
        *,
        domains: list[str],
        max_results: int,
        topic: str,
        fetched_at: datetime,
    ) -> WebSearchProviderResult:
        status = self.get_status()
        if status.availability != "available":
            raise WebSearchNotConfigured(status.detail or "Tavily is unavailable")

        request = {
            "api_key": self.api_key,
            "query": query,
            "topic": topic,
            "search_depth": "basic",
            "max_results": max_results,
            "include_domains": domains,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        try:
            if self.client is not None:
                response = self.client.post(f"{self.base_url}/search", json=request)
            else:
                response = httpx.post(
                    f"{self.base_url}/search",
                    json=request,
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WebSearchProviderError(
                f"Tavily search failed ({type(exc).__name__})"
            ) from exc

        raw_items = payload.get("results")
        if not isinstance(raw_items, list):
            raise WebSearchProviderError("Tavily response did not contain results")

        items: list[WebSearchProviderItem] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                items.append(
                    WebSearchProviderItem(
                        title=str(raw.get("title") or "").strip(),
                        url=str(raw.get("url") or "").strip(),
                        snippet=str(raw.get("content") or "").strip(),
                        published_at=_provider_datetime(
                            raw.get("published_date") or raw.get("publishedAt")
                        ),
                        score=raw.get("score"),
                    )
                )
            except (TypeError, ValueError):
                continue
        return WebSearchProviderResult(
            provider=self.name,
            query=query,
            fetched_at=fetched_at,
            items=items,
        )
