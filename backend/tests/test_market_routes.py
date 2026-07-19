import pytest
from fastapi import HTTPException

from app.connectors.market_data.errors import (
    MarketDataBudgetExceeded,
    MarketDataProviderError,
    MarketDataUnavailable,
)
from app.models.market_data import MarketProviderStatus
from app.routes import market as market_route


class FailingService:
    def __init__(self, error):
        self.error = error

    def new_budget(self):
        return object()

    def get_quotes(self, *args, **kwargs):
        raise self.error


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (ValueError("bad symbol"), 400),
        (MarketDataUnavailable("provider unavailable"), 503),
        (MarketDataBudgetExceeded("budget exhausted"), 429),
        (MarketDataProviderError("upstream failed"), 502),
    ],
)
def test_quote_route_maps_operational_errors(monkeypatch, error, status_code):
    monkeypatch.setattr(market_route, "_service", FailingService(error))
    with pytest.raises(HTTPException) as raised:
        market_route.get_market_quotes("AAPL", "equity")
    assert raised.value.status_code == status_code


def test_provider_status_does_not_make_data_request(monkeypatch):
    expected = MarketProviderStatus(
        availability="available",
        configured_provider="yfinance",
        allowed=True,
        supported_operations=["quote", "history", "profile"],
        supported_asset_types=["equity", "etf"],
    )

    class StatusService:
        def get_provider_status(self):
            return expected

    monkeypatch.setattr(market_route, "_service", StatusService())
    assert market_route.get_market_provider_status() == expected
