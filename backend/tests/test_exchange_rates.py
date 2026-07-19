from datetime import date
from decimal import Decimal

import pytest

from app.connectors.exchange_rates.errors import ExchangeRateProviderError
from app.connectors.exchange_rates.frankfurter_provider import (
    FrankfurterExchangeRateProvider,
)
from app.models.costing import ExchangeRateSnapshot
from app.services.exchange_rates import ExchangeRateService


TODAY = date(2026, 7, 19)


class FakeResponse:
    def __init__(self, payload, *, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


def test_frankfurter_provider_pins_ecb_and_accepts_previous_business_day():
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            {"date": "2026-07-17", "base": "USD", "quote": "CNY", "rate": 6.7775}
        )

    provider = FrankfurterExchangeRateProvider(http_get=fake_get)
    result = provider.get_rate("usd", "cny", on_date=TODAY)

    assert result.exchange_rate == Decimal("6.7775")
    assert result.exchange_rate_date == date(2026, 7, 17)
    assert result.exchange_rate_source == "frankfurter:ECB"
    assert calls[0][1]["params"] == {"date": "2026-07-19", "providers": "ECB"}


@pytest.mark.parametrize(
    "payload",
    [
        {"date": "2026-07-17", "base": "EUR", "quote": "CNY", "rate": 6.7},
        {"date": "2026-07-20", "base": "USD", "quote": "CNY", "rate": 6.7},
        {"date": "2026-07-17", "base": "USD", "quote": "CNY", "rate": 0},
        {"unexpected": "contract"},
    ],
)
def test_frankfurter_provider_rejects_invalid_or_mismatched_contract(payload):
    provider = FrankfurterExchangeRateProvider(
        http_get=lambda *args, **kwargs: FakeResponse(payload)
    )

    with pytest.raises(ExchangeRateProviderError):
        provider.get_rate("USD", "CNY", on_date=TODAY)


def test_exchange_rate_service_prefers_fresh_persisted_snapshot():
    persisted = ExchangeRateSnapshot(
        billing_currency="USD",
        reporting_currency="CNY",
        exchange_rate="6.8",
        exchange_rate_date=date(2026, 7, 17),
        exchange_rate_source="stored-test",
    )

    class Provider:
        def get_rate(self, *args, **kwargs):
            raise AssertionError("fresh snapshot must not make an external call")

    service = ExchangeRateService(
        provider=Provider(),
        snapshot_reader=lambda *args: persisted,
        snapshot_writer=lambda snapshot: True,
        max_snapshot_age_days=3,
    )

    assert service.get_rate("USD", "CNY", on_date=TODAY) == persisted


def test_exchange_rate_service_refreshes_stale_snapshot_and_persists_result():
    stale = ExchangeRateSnapshot(
        billing_currency="USD",
        reporting_currency="CNY",
        exchange_rate="6.6",
        exchange_rate_date=date(2026, 7, 1),
        exchange_rate_source="stored-test",
    )
    refreshed = stale.model_copy(
        update={
            "exchange_rate": Decimal("6.77"),
            "exchange_rate_date": date(2026, 7, 17),
            "exchange_rate_source": "frankfurter:ECB",
        }
    )
    saved = []

    class Provider:
        def get_rate(self, *args, **kwargs):
            return refreshed

    service = ExchangeRateService(
        provider=Provider(),
        snapshot_reader=lambda *args: stale,
        snapshot_writer=lambda snapshot: saved.append(snapshot) or True,
        max_snapshot_age_days=7,
    )

    assert service.get_rate("USD", "CNY", on_date=TODAY) == refreshed
    assert saved == [refreshed]


def test_exchange_rate_service_uses_identity_without_database_or_provider():
    class Provider:
        def get_rate(self, *args, **kwargs):
            raise AssertionError("identity rate must not call provider")

    service = ExchangeRateService(
        provider=Provider(),
        snapshot_reader=lambda *args: (_ for _ in ()).throw(
            AssertionError("identity rate must not query database")
        ),
        snapshot_writer=lambda snapshot: False,
    )

    result = service.get_rate("CNY", "CNY", on_date=TODAY)
    assert result.exchange_rate == Decimal("1")
    assert result.exchange_rate_source == "identity"
