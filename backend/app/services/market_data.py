"""Cache-first, budgeted orchestration for read-only market data."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from app.connectors.market_data.errors import MarketDataUnavailable
from app.connectors.market_data.provider import MarketDataProvider, MarketResearchProvider
from app.models.investments import MarketInstrument, MarketQuote, MarketQuoteBatch
from app.models.market_data import (
    MarketAssetType,
    MarketCacheEntry,
    MarketCacheMetadata,
    MarketInstrumentData,
    MarketInstrumentProfile,
    MarketPriceBar,
    MarketPriceHistory,
    MarketProviderStatus,
    MarketQuoteResult,
)
from app.runtime.policy.market_outbound_policy import OutboundCallBudget


CacheReader = Callable[..., MarketCacheEntry | None]
CacheWriter = Callable[[MarketCacheEntry], bool]
QuoteWriter = Callable[[MarketQuote], bool]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketDataService:
    def __init__(
        self,
        *,
        quote_provider: MarketDataProvider,
        research_provider: MarketResearchProvider,
        cache_reader: CacheReader,
        cache_writer: CacheWriter,
        quote_writer: QuoteWriter,
        quote_ttl_seconds: int = 180,
        history_ttl_seconds: int = 86400,
        profile_ttl_seconds: int = 604800,
        symbol_limit: int = 20,
        history_day_limit: int = 3660,
        outbound_call_budget: int = 3,
        clock: Clock = _utc_now,
    ) -> None:
        self.quote_provider = quote_provider
        self.research_provider = research_provider
        self.cache_reader = cache_reader
        self.cache_writer = cache_writer
        self.quote_writer = quote_writer
        self.quote_ttl_seconds = quote_ttl_seconds
        self.history_ttl_seconds = history_ttl_seconds
        self.profile_ttl_seconds = profile_ttl_seconds
        self.symbol_limit = symbol_limit
        self.history_day_limit = history_day_limit
        self.outbound_call_budget = outbound_call_budget
        self.clock = clock

    def new_budget(self) -> OutboundCallBudget:
        return OutboundCallBudget(self.outbound_call_budget)

    def get_provider_status(self) -> MarketProviderStatus:
        return self.research_provider.get_status()

    def _provider_name(self) -> str:
        return self.get_provider_status().configured_provider

    def _ensure_available(self) -> MarketProviderStatus:
        status = self.get_provider_status()
        if status.availability != "available" or not status.allowed:
            raise MarketDataUnavailable(status.detail or "market data provider unavailable")
        return status

    @staticmethod
    def _key(operation: str, provider: str, parameters: dict) -> str:
        canonical = json.dumps(
            {
                "operation": operation,
                "provider": provider,
                "parameters": parameters,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _cache_metadata(
        entry: MarketCacheEntry,
        *,
        cache_hit: bool,
    ) -> MarketCacheMetadata:
        return MarketCacheMetadata(
            cache_hit=cache_hit,
            cache_key=entry.cache_key,
            provider=entry.provider,
            fetched_at=entry.fetched_at,
            expires_at=entry.expires_at,
        )

    def _cache_read(self, cache_key: str, *, now: datetime) -> MarketCacheEntry | None:
        return self.cache_reader(cache_key, now=now)

    def _cache_entry(
        self,
        *,
        cache_key: str,
        operation: str,
        provider: str,
        payload: dict,
        fetched_at: datetime,
        ttl_seconds: int,
    ) -> MarketCacheEntry:
        return MarketCacheEntry(
            cache_key=cache_key,
            operation=operation,
            provider=provider,
            payload=payload,
            fetched_at=fetched_at,
            expires_at=fetched_at + timedelta(seconds=ttl_seconds),
        )

    def get_quotes(
        self,
        symbols: list[str],
        *,
        asset_type: MarketAssetType,
        budget: OutboundCallBudget,
    ) -> MarketQuoteResult:
        normalized = list(
            dict.fromkeys(
                MarketInstrument(symbol=symbol, asset_type=asset_type).symbol
                for symbol in symbols
            )
        )
        if not normalized:
            raise ValueError("at least one symbol is required")
        if len(normalized) > self.symbol_limit:
            raise ValueError(f"symbol count cannot exceed {self.symbol_limit}")

        provider = self._provider_name()
        cache_key = self._key(
            "quote",
            provider,
            {"asset_type": asset_type, "symbols": sorted(normalized)},
        )
        now = self.clock()
        cached = self._cache_read(cache_key, now=now)
        if cached is not None:
            batch = MarketQuoteBatch.model_validate(cached.payload)
            return MarketQuoteResult(
                provider=batch.provider,
                fetched_at=cached.fetched_at,
                quotes=batch.quotes,
                missing=batch.missing,
                cache=self._cache_metadata(cached, cache_hit=True),
                external_calls=budget.snapshot(),
            )

        self._ensure_available()
        budget.consume()
        instruments = [
            MarketInstrument(symbol=symbol, asset_type=asset_type)
            for symbol in normalized
        ]
        batch = self.quote_provider.get_latest_quotes(instruments, as_of=now)
        fetched_at = self.clock()
        entry = self._cache_entry(
            cache_key=cache_key,
            operation="quote",
            provider=provider,
            payload=batch.model_dump(mode="json"),
            fetched_at=fetched_at,
            ttl_seconds=self.quote_ttl_seconds,
        )
        self.cache_writer(entry)
        for quote in batch.quotes:
            self.quote_writer(quote)
        return MarketQuoteResult(
            provider=batch.provider,
            fetched_at=fetched_at,
            quotes=batch.quotes,
            missing=batch.missing,
            cache=self._cache_metadata(entry, cache_hit=False),
            external_calls=budget.snapshot(),
        )

    def get_profile(
        self,
        symbol: str,
        *,
        asset_type: MarketAssetType,
        budget: OutboundCallBudget,
    ) -> MarketInstrumentProfile:
        instrument = MarketInstrument(symbol=symbol, asset_type=asset_type)
        provider = self._provider_name()
        cache_key = self._key(
            "profile",
            provider,
            {"asset_type": asset_type, "symbol": instrument.symbol},
        )
        now = self.clock()
        cached = self._cache_read(cache_key, now=now)
        if cached is not None:
            data = MarketInstrumentData.model_validate(cached.payload)
            return MarketInstrumentProfile(
                **data.model_dump(),
                cache=self._cache_metadata(cached, cache_hit=True),
                external_calls=budget.snapshot(),
            )

        self._ensure_available()
        budget.consume()
        fetched_at = self.clock()
        data = self.research_provider.get_instrument_profile(
            instrument.symbol,
            asset_type=asset_type,
            fetched_at=fetched_at,
        )
        entry = self._cache_entry(
            cache_key=cache_key,
            operation="profile",
            provider=provider,
            payload=data.model_dump(mode="json"),
            fetched_at=fetched_at,
            ttl_seconds=self.profile_ttl_seconds,
        )
        self.cache_writer(entry)
        return MarketInstrumentProfile(
            **data.model_dump(),
            cache=self._cache_metadata(entry, cache_hit=False),
            external_calls=budget.snapshot(),
        )

    def get_history(
        self,
        symbol: str,
        *,
        asset_type: MarketAssetType,
        date_from: date,
        date_to: date,
        budget: OutboundCallBudget,
    ) -> MarketPriceHistory:
        if date_from > date_to:
            raise ValueError("date_from must be on or before date_to")
        if (date_to - date_from).days > self.history_day_limit:
            raise ValueError(
                f"market history range cannot exceed {self.history_day_limit} days"
            )
        instrument = MarketInstrument(symbol=symbol, asset_type=asset_type)
        provider = self._provider_name()
        cache_key = self._key(
            "history",
            provider,
            {
                "asset_type": asset_type,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "interval": "1d",
                "symbol": instrument.symbol,
            },
        )
        now = self.clock()
        cached = self._cache_read(cache_key, now=now)
        if cached is not None:
            bars = [MarketPriceBar.model_validate(item) for item in cached.payload["bars"]]
            return MarketPriceHistory(
                symbol=instrument.symbol,
                asset_type=asset_type,
                provider=str(cached.payload["provider"]),
                currency=str(cached.payload["currency"]),
                date_from=date_from,
                date_to=date_to,
                fetched_at=cached.fetched_at,
                bars=bars,
                cache=self._cache_metadata(cached, cache_hit=True),
                external_calls=budget.snapshot(),
            )

        profile = self.get_profile(
            instrument.symbol,
            asset_type=asset_type,
            budget=budget,
        )
        self._ensure_available()
        budget.consume()
        bars = self.research_provider.get_price_history(
            instrument.symbol,
            asset_type=asset_type,
            date_from=date_from,
            date_to=date_to,
            currency=profile.currency,
        )
        fetched_at = self.clock()
        source = bars[0].source if bars else f"openbb:{provider}"
        payload = {
            "provider": source,
            "currency": profile.currency,
            "bars": [bar.model_dump(mode="json") for bar in bars],
        }
        entry = self._cache_entry(
            cache_key=cache_key,
            operation="history",
            provider=provider,
            payload=payload,
            fetched_at=fetched_at,
            ttl_seconds=self.history_ttl_seconds,
        )
        self.cache_writer(entry)
        return MarketPriceHistory(
            symbol=instrument.symbol,
            asset_type=asset_type,
            provider=source,
            currency=profile.currency,
            date_from=date_from,
            date_to=date_to,
            fetched_at=fetched_at,
            bars=bars,
            cache=self._cache_metadata(entry, cache_hit=False),
            external_calls=budget.snapshot(),
        )
