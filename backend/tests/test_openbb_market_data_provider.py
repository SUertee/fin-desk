from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.connectors.market_data.openbb_provider import OpenBBMarketDataProvider
from app.models.investments import MarketInstrument


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


class FakePrice:
    def quote(self, **kwargs):
        assert kwargs == {"symbol": ["AAPL"], "provider": "yfinance"}
        return SimpleNamespace(
            provider="yfinance",
            results=[
                {
                    "symbol": "AAPL",
                    "last_price": 205.125,
                    "currency": "USD",
                    "last_timestamp": NOW,
                    "exchange": "NMS",
                }
            ],
        )

    def historical(self, **kwargs):
        assert kwargs["interval"] == "1d"
        return SimpleNamespace(
            provider="yfinance",
            results=[
                {
                    "date": date(2026, 7, 18),
                    "open": 200,
                    "high": 210,
                    "low": 198,
                    "close": 205.125,
                    "volume": 1234,
                }
            ],
        )


class FakeEquity:
    def __init__(self):
        self.price = FakePrice()

    def profile(self, **kwargs):
        assert kwargs == {"symbol": "AAPL", "provider": "yfinance"}
        return SimpleNamespace(
            provider="yfinance",
            results=[
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "exchange": "NMS",
                    "currency": "USD",
                    "sector": "Technology",
                    "industry": "Consumer Electronics",
                    "country": "United States",
                }
            ],
        )


def _provider():
    client = SimpleNamespace(equity=FakeEquity())
    return OpenBBMarketDataProvider(client_factory=lambda: client)


def test_openbb_quote_is_normalized_to_findesk_contract():
    batch = _provider().get_latest_quotes(
        [MarketInstrument(symbol="AAPL", asset_type="equity")],
        as_of=NOW,
    )
    assert batch.provider == "openbb:yfinance"
    assert batch.quotes[0].price.amount.as_tuple().exponent == -3
    assert batch.quotes[0].source == "openbb:yfinance"
    assert batch.quotes[0].venue == "NMS"


def test_openbb_quote_without_timestamp_is_explicitly_retrieval_timed():
    client = SimpleNamespace(
        equity=SimpleNamespace(
            price=SimpleNamespace(
                quote=lambda **_: SimpleNamespace(
                    provider="yfinance",
                    results=[{"symbol": "AAPL", "last_price": 205, "currency": "USD"}],
                )
            )
        )
    )
    provider = OpenBBMarketDataProvider(client_factory=lambda: client)
    instrument = MarketInstrument(symbol="AAPL", asset_type="equity")
    batch = provider.get_latest_quotes([instrument], as_of=NOW)
    assert batch.missing == []
    assert batch.quotes[0].timestamp_basis == "retrieval_time"
    assert batch.quotes[0].quote_as_of == NOW


def test_openbb_quote_skips_malformed_provider_records():
    client = SimpleNamespace(
        equity=SimpleNamespace(
            price=SimpleNamespace(
                quote=lambda **_: SimpleNamespace(
                    provider="yfinance",
                    results=[
                        {"symbol": "", "last_price": 1, "currency": "USD"},
                        {
                            "symbol": "AAPL",
                            "last_price": 205,
                            "currency": "USD",
                            "last_timestamp": NOW,
                        },
                    ],
                )
            )
        )
    )
    provider = OpenBBMarketDataProvider(client_factory=lambda: client)
    instrument = MarketInstrument(symbol="AAPL", asset_type="equity")
    batch = provider.get_latest_quotes([instrument], as_of=NOW)
    assert [quote.symbol for quote in batch.quotes] == ["AAPL"]
    assert batch.missing == []


def test_openbb_profile_and_history_are_normalized():
    provider = _provider()
    profile = provider.get_instrument_profile(
        "aapl", asset_type="equity", fetched_at=NOW
    )
    bars = provider.get_price_history(
        "AAPL",
        asset_type="equity",
        date_from=date(2026, 7, 18),
        date_to=date(2026, 7, 18),
        currency=profile.currency,
    )
    assert profile.name == "Apple Inc."
    assert profile.currency == "USD"
    assert bars[0].close.amount.as_tuple().exponent == -3
    assert bars[0].source == "openbb:yfinance"


def test_disallowed_provider_status_does_not_load_client():
    called = False

    def factory():
        nonlocal called
        called = True
        return object()

    status = OpenBBMarketDataProvider(
        provider="fmp",
        allowed_providers=("yfinance",),
        client_factory=factory,
    ).get_status()
    assert status.availability == "unavailable"
    assert status.allowed is False
    assert called is False
