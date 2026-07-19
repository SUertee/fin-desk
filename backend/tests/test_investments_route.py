from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.investments import PortfolioSnapshot
from app.routes import investments as investments_route


NOW = datetime.now(timezone.utc).replace(microsecond=0)


class FakePortfolioService:
    def __init__(self):
        self.calls = []

    def get_snapshot(self, user_id, *, as_of, reporting_currency):
        self.calls.append((user_id, as_of, reporting_currency))
        return PortfolioSnapshot(
            user_id=user_id,
            status="empty",
            as_of=as_of,
            reporting_currency=reporting_currency,
        )


@pytest.fixture
def service(monkeypatch):
    fake = FakePortfolioService()
    monkeypatch.setattr(investments_route, "_service", fake)
    return fake


def test_portfolio_route_passes_user_as_of_and_normalized_currency(service):
    result = investments_route.get_portfolio(
        "demo", as_of=NOW, reporting_currency="aud"
    )

    assert result.status == "empty"
    assert service.calls == [("demo", NOW, "AUD")]


def test_portfolio_route_rejects_future_as_of(service):
    with pytest.raises(HTTPException) as exc:
        investments_route.get_portfolio(
            "demo", as_of=NOW + timedelta(days=1), reporting_currency="CNY"
        )

    assert exc.value.status_code == 400
    assert service.calls == []


def test_portfolio_route_rejects_invalid_currency(service):
    with pytest.raises(HTTPException) as exc:
        investments_route.get_portfolio(
            "demo", as_of=NOW, reporting_currency="CN"
        )

    assert exc.value.status_code == 400
    assert service.calls == []
