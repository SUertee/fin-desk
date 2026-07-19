from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models.costing import ExchangeRateSnapshot
from app.models.investments import (
    InvestmentAccount,
    InvestmentPosition,
    MarketQuote,
    MarketQuoteBatch,
)
from app.services.investment_portfolio import PortfolioService


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


class FakeMarketDataProvider:
    def __init__(self, quotes):
        self.quotes = quotes
        self.calls = []

    def get_latest_quotes(self, instruments, *, as_of):
        self.calls.append((instruments, as_of))
        found = {quote.instrument for quote in self.quotes}
        return MarketQuoteBatch(
            provider="fake",
            as_of=as_of,
            quotes=self.quotes,
            missing=[item for item in instruments if item not in found],
        )


def _account():
    return InvestmentAccount(
        user_id="demo",
        account_id="broker-1",
        name="Brokerage",
        base_currency="USD",
        as_of=NOW,
    )


def _position(symbol, quantity="1"):
    return InvestmentPosition(
        user_id="demo",
        account_id="broker-1",
        symbol=symbol,
        asset_type="equity",
        quantity=quantity,
        as_of=NOW,
    )


def _quote(symbol, amount, currency="USD", age_days=0):
    return MarketQuote(
        symbol=symbol,
        asset_type="equity",
        price={"amount": str(amount), "currency": currency},
        quote_as_of=NOW - timedelta(days=age_days),
        source="recorded-test-feed",
    )


def _rate(billing, reporting, accounting_date):
    if billing == reporting:
        return ExchangeRateSnapshot(
            billing_currency=billing,
            reporting_currency=reporting,
            exchange_rate="1",
            exchange_rate_date=accounting_date,
            exchange_rate_source="identity",
        )
    if (billing, reporting) == ("USD", "CNY"):
        return ExchangeRateSnapshot(
            billing_currency="USD",
            reporting_currency="CNY",
            exchange_rate="7.2",
            exchange_rate_date=date(2026, 7, 18),
            exchange_rate_source="recorded-test-fx",
        )
    return None


def _service(positions, quotes, rate_lookup=_rate):
    return PortfolioService(
        account_reader=lambda user_id, limit: [_account()] if user_id == "demo" else [],
        position_reader=lambda user_id, limit: positions if user_id == "demo" else [],
        market_data_provider=FakeMarketDataProvider(quotes),
        exchange_rate_lookup=rate_lookup,
        stale_after_days=3,
        concentration_threshold_percent=Decimal("80"),
    )


def test_complete_portfolio_preserves_native_and_reporting_values():
    service = _service(
        [_position("AAPL", "2"), _position("BND", "10")],
        [_quote("AAPL", "100"), _quote("BND", "5", "CNY")],
    )

    snapshot = service.get_snapshot(
        "demo", as_of=NOW, reporting_currency="CNY"
    )

    assert snapshot.status == "complete"
    assert snapshot.reporting_total.amount == Decimal("1490.0")
    assert [(item.currency, item.amount) for item in snapshot.native_totals] == [
        ("CNY", Decimal("50")),
        ("USD", Decimal("200")),
    ]
    assert snapshot.coverage.reporting_position_count == 2
    assert snapshot.coverage.quote_sources == ["recorded-test-feed"]


def test_missing_quote_is_partial_and_does_not_fabricate_complete_total():
    service = _service(
        [_position("AAPL"), _position("UNKNOWN")],
        [_quote("AAPL", "100")],
    )

    snapshot = service.get_snapshot(
        "demo", as_of=NOW, reporting_currency="CNY"
    )

    assert snapshot.status == "partial"
    assert snapshot.reporting_total is None
    assert snapshot.converted_subtotal.amount == Decimal("720.0")
    assert "missing_quote" in [finding.code for finding in snapshot.risk.findings]


def test_missing_exchange_rate_keeps_native_value_and_marks_partial():
    service = _service(
        [_position("AAPL")],
        [_quote("AAPL", "100", "AUD")],
        rate_lookup=lambda *_: None,
    )

    snapshot = service.get_snapshot(
        "demo", as_of=NOW, reporting_currency="CNY"
    )

    assert snapshot.status == "partial"
    assert snapshot.native_totals[0].amount == Decimal("100")
    assert snapshot.converted_subtotal is None
    assert snapshot.reporting_total is None
    assert "missing_exchange_rate" in [
        finding.code for finding in snapshot.risk.findings
    ]


def test_empty_portfolio_is_not_reported_as_zero_invested_value():
    service = _service([], [])

    snapshot = service.get_snapshot(
        "demo", as_of=NOW, reporting_currency="CNY"
    )

    assert snapshot.status == "empty"
    assert snapshot.reporting_total is None
    assert snapshot.converted_subtotal is None
    assert snapshot.positions == []
