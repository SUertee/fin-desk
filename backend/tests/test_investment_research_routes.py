from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.connectors.market_data.errors import (
    MarketDataBudgetExceeded,
    MarketDataProviderError,
    MarketDataUnavailable,
)
from app.models.investment_research import InvestmentScenarioRequest
from app.routes import investment_research as route


class FailingService:
    def __init__(self, error):
        self.error = error

    def get_instrument_research(self, *args, **kwargs):
        raise self.error


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (ValueError("bad symbol"), 400),
        (LookupError("scenario not found"), 404),
        (MarketDataUnavailable("provider unavailable"), 503),
        (MarketDataBudgetExceeded("budget exhausted"), 429),
        (MarketDataProviderError("upstream failed"), 502),
        (RuntimeError("database unavailable"), 503),
    ],
)
def test_research_route_maps_operational_errors(monkeypatch, error, status_code):
    monkeypatch.setattr(route, "_service", FailingService(error))

    with pytest.raises(HTTPException) as raised:
        route.get_instrument_research("demo", "AAPL", "equity", None, None)

    assert raised.value.status_code == status_code


def test_scenario_request_keeps_hypothetical_cash_separate_from_holdings():
    request = InvestmentScenarioRequest(
        name="Paper research",
        reporting_currency="CNY",
        starting_cash_amount="10000",
    )

    assert request.starting_cash_amount == 10000
    assert not hasattr(request, "account_id")
    assert not hasattr(request, "order_type")


def test_scenario_valuation_rejects_future_as_of_before_service(monkeypatch):
    future = datetime(2030, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(HTTPException) as raised:
        route.get_scenario_valuation("demo", "scenario-1", future)

    assert raised.value.status_code == 400
