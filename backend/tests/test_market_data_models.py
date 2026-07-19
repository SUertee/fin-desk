from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.market_data import (
    ExternalCallUsage,
    MarketCacheMetadata,
    MarketPriceBar,
)


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


def _bar(**overrides):
    values = {
        "symbol": "aapl",
        "asset_type": "equity",
        "period": date(2026, 7, 18),
        "open": {"amount": "200", "currency": "USD"},
        "high": {"amount": "210", "currency": "USD"},
        "low": {"amount": "198", "currency": "USD"},
        "close": {"amount": "205", "currency": "USD"},
        "volume": 1000,
        "source": "openbb:yfinance",
    }
    values.update(overrides)
    return MarketPriceBar(**values)


def test_price_bar_normalizes_symbol_and_preserves_decimal_money():
    bar = _bar()
    assert bar.symbol == "AAPL"
    assert str(bar.close.amount) == "205"


def test_price_bar_rejects_mixed_currencies():
    with pytest.raises(ValidationError, match="currencies must match"):
        _bar(close={"amount": "205", "currency": "CNY"})


def test_cache_metadata_rejects_non_positive_ttl():
    with pytest.raises(ValidationError, match="expiry must be after"):
        MarketCacheMetadata(
            cache_hit=False,
            cache_key="a" * 64,
            provider="yfinance",
            fetched_at=NOW,
            expires_at=NOW,
        )


def test_external_call_usage_must_balance():
    with pytest.raises(ValidationError, match="must balance"):
        ExternalCallUsage(budget=3, used=1, remaining=1)
