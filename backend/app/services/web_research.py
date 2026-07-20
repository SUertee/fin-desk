"""Cache-first governance service for external web research."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.config.settings import WebResearchSettings, get_settings
from app.connectors.postgres.web_research_cache_store import (
    get_web_research_cache_db,
    save_web_research_cache_db,
)
from app.connectors.web_search import (
    TavilyWebSearchProvider,
    WebSearchBudgetExceeded,
    WebSearchNotConfigured,
    WebSearchProvider,
    WebSearchProviderError,
)
from app.models.market_data import ExternalCallUsage
from app.models.web_research import (
    WebResearchCacheEntry,
    WebResearchCacheMetadata,
    WebResearchItem,
    WebResearchRequest,
    WebResearchResult,
    WebSearchProviderStatus,
    source_domain,
)


@dataclass
class WebResearchBudget:
    limit: int
    used: int = 0

    def consume(self) -> None:
        if self.used >= self.limit:
            raise WebSearchBudgetExceeded("web-research outbound budget exhausted")
        self.used += 1

    def snapshot(self) -> ExternalCallUsage:
        return ExternalCallUsage(
            budget=self.limit,
            used=self.used,
            remaining=self.limit - self.used,
        )


class WebResearchService:
    def __init__(
        self,
        provider: WebSearchProvider,
        *,
        settings: WebResearchSettings,
        cache_reader: Callable[
            ..., WebResearchCacheEntry | None
        ] = get_web_research_cache_db,
        cache_writer: Callable[
            [WebResearchCacheEntry], bool
        ] = save_web_research_cache_db,
        clock: Callable[[], datetime] | None = None,
    ):
        self.provider = provider
        self.settings = settings
        self.cache_reader = cache_reader
        self.cache_writer = cache_writer
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def new_budget(self) -> WebResearchBudget:
        return WebResearchBudget(limit=self.settings.outbound_call_budget)

    def get_provider_status(self) -> WebSearchProviderStatus:
        return self.provider.get_status()

    @staticmethod
    def _domain_allowed(domain: str, allowed: tuple[str, ...]) -> bool:
        return any(domain == item or domain.endswith(f".{item}") for item in allowed)

    def _scope(self, requested: list[str]) -> tuple[str, ...]:
        if not requested:
            return self.settings.allowed_domains
        disallowed = [
            domain
            for domain in requested
            if not self._domain_allowed(domain, self.settings.allowed_domains)
        ]
        if disallowed:
            raise ValueError(
                "requested domains are not allowlisted: " + ", ".join(disallowed)
            )
        return tuple(requested)

    @staticmethod
    def _cache_key(request: WebResearchRequest, domains: tuple[str, ...]) -> str:
        canonical = json.dumps(
            {
                "query": request.query.casefold(),
                "domains": sorted(domains),
                "max_results": request.max_results,
                "topic": request.topic,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _unavailable(
        self,
        request: WebResearchRequest,
        budget: WebResearchBudget,
        limitation: str,
    ) -> WebResearchResult:
        return WebResearchResult(
            status="unavailable",
            provider=self.get_provider_status().configured_provider,
            query=request.query,
            limitations=[limitation],
            external_calls=budget.snapshot(),
        )

    def search(
        self,
        request: WebResearchRequest | dict,
        *,
        budget: WebResearchBudget,
    ) -> WebResearchResult:
        parsed = WebResearchRequest.model_validate(request)
        if parsed.max_results > self.settings.max_results:
            raise ValueError(
                f"max_results cannot exceed configured limit {self.settings.max_results}"
            )
        domains = self._scope(parsed.domains)
        cache_key = self._cache_key(parsed, domains)
        now = self.clock()
        cached = self.cache_reader(cache_key, now=now)
        if cached is not None:
            result = WebResearchResult.model_validate(cached.payload)
            return result.model_copy(
                update={
                    "cache": WebResearchCacheMetadata(
                        cache_hit=True,
                        cache_key=cache_key,
                        fetched_at=cached.fetched_at,
                        expires_at=cached.expires_at,
                    ),
                    "external_calls": budget.snapshot(),
                }
            )

        status = self.get_provider_status()
        if status.availability != "available" or not status.allowed:
            return self._unavailable(
                parsed,
                budget,
                status.detail or "web research provider is unavailable",
            )

        try:
            budget.consume()
            provider_result = self.provider.search(
                parsed.query,
                domains=list(domains),
                max_results=parsed.max_results,
                topic=parsed.topic,
                fetched_at=now,
            )
        except WebSearchBudgetExceeded:
            raise
        except (WebSearchNotConfigured, WebSearchProviderError) as exc:
            return self._unavailable(parsed, budget, str(exc))

        items: list[WebResearchItem] = []
        excluded = 0
        for item in provider_result.items:
            try:
                domain = source_domain(item.url)
            except ValueError:
                excluded += 1
                continue
            if not self._domain_allowed(domain, domains):
                excluded += 1
                continue
            result_id = hashlib.sha256(item.url.encode("utf-8")).hexdigest()[:24]
            items.append(
                WebResearchItem(
                    result_id=result_id,
                    title=item.title,
                    url=item.url,
                    domain=domain,
                    snippet=item.snippet,
                    provider=provider_result.provider,
                    published_at=item.published_at,
                    fetched_at=provider_result.fetched_at,
                    score=item.score,
                )
            )
        limitations: list[str] = []
        if excluded:
            limitations.append(
                f"{excluded} provider results were excluded by source governance."
            )
        if not items:
            limitations.append("No allowlisted sources matched the query.")
        result_status = (
            "available"
            if items and not excluded
            else "partial"
            if items
            else "unavailable"
        )
        expires_at = provider_result.fetched_at + timedelta(
            seconds=self.settings.cache_ttl_seconds
        )
        result = WebResearchResult(
            status=result_status,
            provider=provider_result.provider,
            query=parsed.query,
            items=items,
            excluded_count=excluded,
            limitations=limitations,
            cache=WebResearchCacheMetadata(
                cache_hit=False,
                cache_key=cache_key,
                fetched_at=provider_result.fetched_at,
                expires_at=expires_at,
            ),
            external_calls=budget.snapshot(),
        )
        self.cache_writer(
            WebResearchCacheEntry(
                cache_key=cache_key,
                provider=provider_result.provider,
                payload=result.model_dump(mode="json"),
                fetched_at=provider_result.fetched_at,
                expires_at=expires_at,
            )
        )
        return result


def build_web_research_service() -> WebResearchService:
    settings = get_settings().web_research
    provider = TavilyWebSearchProvider(
        api_key=os.getenv("TAVILY_API_KEY", ""),
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        allowed=settings.provider in settings.allowed_providers,
    )
    return WebResearchService(provider, settings=settings)
