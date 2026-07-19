from datetime import date, datetime, timezone

from app.models.costing import MoneyAmount
from app.models.investments import MarketQuote, MarketQuoteBatch
from app.models.market_data import (
    MarketInstrumentData,
    MarketPriceBar,
    MarketProviderStatus,
)
from app.services.market_data import MarketDataService


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self):
        self.quote_calls = 0
        self.profile_calls = 0
        self.history_calls = 0

    def get_status(self):
        return MarketProviderStatus(
            availability="available",
            configured_provider="yfinance",
            allowed=True,
            supported_operations=["quote", "history", "profile"],
            supported_asset_types=["equity", "etf"],
        )

    def get_latest_quotes(self, instruments, *, as_of):
        self.quote_calls += 1
        quote = MarketQuote(
            symbol=instruments[0].symbol,
            asset_type=instruments[0].asset_type,
            price=MoneyAmount(amount="205", currency="USD"),
            quote_as_of=NOW,
            source="openbb:yfinance",
            venue="NMS",
        )
        return MarketQuoteBatch(
            provider="openbb:yfinance", as_of=as_of, quotes=[quote]
        )

    def get_instrument_profile(self, symbol, *, asset_type, fetched_at):
        self.profile_calls += 1
        return MarketInstrumentData(
            symbol=symbol,
            asset_type=asset_type,
            name="Apple Inc.",
            venue="NMS",
            currency="USD",
            source="openbb:yfinance",
            fetched_at=fetched_at,
        )

    def get_price_history(
        self, symbol, *, asset_type, date_from, date_to, currency
    ):
        self.history_calls += 1
        return [
            MarketPriceBar(
                symbol=symbol,
                asset_type=asset_type,
                period=date_from,
                open={"amount": "200", "currency": currency},
                high={"amount": "210", "currency": currency},
                low={"amount": "198", "currency": currency},
                close={"amount": "205", "currency": currency},
                source="openbb:yfinance",
            )
        ]


class MemoryCache:
    def __init__(self):
        self.entries = {}

    def read(self, key, *, now):
        entry = self.entries.get(key)
        return entry if entry and entry.expires_at > now else None

    def write(self, entry):
        self.entries[entry.cache_key] = entry
        return True


def _service(provider=None, cache=None, quote_writer=None):
    provider = provider or FakeProvider()
    cache = cache or MemoryCache()
    return (
        MarketDataService(
            quote_provider=provider,
            research_provider=provider,
            cache_reader=cache.read,
            cache_writer=cache.write,
            quote_writer=quote_writer or (lambda _: True),
            clock=lambda: NOW,
        ),
        provider,
        cache,
    )


def test_quote_cache_hit_does_not_consume_budget_or_call_provider():
    service, provider, _ = _service()
    first = service.get_quotes(
        ["aapl"], asset_type="equity", budget=service.new_budget()
    )
    second_budget = service.new_budget()
    second = service.get_quotes(
        ["AAPL"], asset_type="equity", budget=second_budget
    )
    assert first.cache.cache_hit is False
    assert second.cache.cache_hit is True
    assert second.external_calls.used == 0
    assert provider.quote_calls == 1


def test_successful_external_quote_is_persisted_as_immutable_evidence():
    saved = []
    service, _, _ = _service(quote_writer=lambda quote: saved.append(quote) or True)
    result = service.get_quotes(
        ["AAPL"], asset_type="equity", budget=service.new_budget()
    )
    assert result.external_calls.used == 1
    assert saved == result.quotes


def test_history_uses_profile_currency_and_two_budget_units_on_cold_cache():
    service, provider, _ = _service()
    budget = service.new_budget()
    result = service.get_history(
        "AAPL",
        asset_type="equity",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 18),
        budget=budget,
    )
    assert result.currency == "USD"
    assert result.external_calls.used == 2
    assert provider.profile_calls == 1
    assert provider.history_calls == 1


def test_history_range_is_rejected_before_provider_call():
    service, provider, _ = _service()
    service.history_day_limit = 30
    try:
        service.get_history(
            "AAPL",
            asset_type="equity",
            date_from=date(2026, 1, 1),
            date_to=date(2026, 7, 18),
            budget=service.new_budget(),
        )
    except ValueError as exc:
        assert "cannot exceed" in str(exc)
    else:
        raise AssertionError("expected bounded history validation")
    assert provider.profile_calls == 0
    assert provider.history_calls == 0
