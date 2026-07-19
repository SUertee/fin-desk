from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models.costing import ExchangeRateSnapshot
from app.models.investment_research import (
    InvestmentScenario,
    InvestmentScenarioDetail,
    ScenarioPosition,
)
from app.models.investments import MarketQuote
from app.models.market_data import (
    ExternalCallUsage,
    MarketCacheMetadata,
    MarketInstrumentProfile,
    MarketPriceBar,
    MarketPriceHistory,
    MarketQuoteResult,
)
from app.services.investment_research import InvestmentResearchService
from app.models.user import UserProfile


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


def _cache(operation="profile"):
    return MarketCacheMetadata(
        cache_hit=False,
        cache_key=(operation * 16)[:64],
        provider="fake",
        fetched_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _usage():
    return ExternalCallUsage(budget=3, used=0, remaining=3)


def _quote(symbol, amount, *, timestamp_basis="provider_time"):
    return MarketQuote(
        symbol=symbol,
        asset_type="equity",
        price={"amount": str(amount), "currency": "USD"},
        quote_as_of=NOW,
        timestamp_basis=timestamp_basis,
        source="openbb:yfinance",
    )


class FakeMarketData:
    def __init__(self, quotes=None, histories=None):
        self.quotes = quotes or []
        self.histories = histories or {}
        self.calls = []
        self.budget = object()

    def new_budget(self):
        return self.budget

    def get_profile(self, symbol, *, asset_type, budget):
        self.calls.append(("profile", symbol, budget))
        return MarketInstrumentProfile(
            symbol=symbol,
            asset_type=asset_type,
            name=f"{symbol} Incorporated",
            venue="NASDAQ",
            currency="USD",
            sector="Technology",
            source="openbb:yfinance",
            fetched_at=NOW,
            cache=_cache("profile"),
            external_calls=_usage(),
        )

    def get_quotes(self, symbols, *, asset_type, budget):
        self.calls.append(("quotes", tuple(symbols), budget))
        found = [item for item in self.quotes if item.symbol in symbols]
        return MarketQuoteResult(
            provider="yfinance",
            fetched_at=NOW,
            quotes=found,
            missing=[
                {"symbol": symbol, "asset_type": asset_type}
                for symbol in symbols
                if symbol not in {item.symbol for item in found}
            ],
            cache=_cache("quote"),
            external_calls=_usage(),
        )

    def get_history(self, symbol, *, asset_type, date_from, date_to, budget):
        self.calls.append(("history", symbol, budget))
        if symbol in self.histories:
            return self.histories[symbol]
        return MarketPriceHistory(
            symbol=symbol,
            asset_type=asset_type,
            provider="openbb:yfinance",
            currency="USD",
            date_from=date_from,
            date_to=date_to,
            fetched_at=NOW,
            bars=[],
            cache=_cache("history"),
            external_calls=_usage(),
        )


def _history(symbol, prices, *, asset_type="equity"):
    bars = []
    for index, price in enumerate(prices):
        amount = {"amount": str(price), "currency": "USD"}
        bars.append(
            MarketPriceBar(
                symbol=symbol,
                asset_type=asset_type,
                period=date(2026, 6, 1) + timedelta(days=index),
                open=amount,
                high=amount,
                low=amount,
                close=amount,
                source="fake",
            )
        )
    return MarketPriceHistory(
        symbol=symbol,
        asset_type=asset_type,
        provider="openbb:yfinance",
        currency="USD",
        date_from=date(2026, 6, 1),
        date_to=date(2026, 7, 19),
        fetched_at=NOW,
        bars=bars,
        cache=_cache(f"history-{symbol}"),
        external_calls=_usage(),
    )


class FakeExchangeRates:
    def __init__(self, *, available=True):
        self.available = available

    def get_rate(self, billing, reporting, *, on_date):
        if not self.available:
            from app.connectors.exchange_rates.errors import ExchangeRateUnavailable

            raise ExchangeRateUnavailable("missing test rate")
        return ExchangeRateSnapshot(
            billing_currency=billing,
            reporting_currency=reporting,
            exchange_rate="1" if billing == reporting else "7",
            exchange_rate_date=on_date,
            exchange_rate_source="identity" if billing == reporting else "test-fx",
        )


def _scenario(positions, *, starting_cash="1000"):
    scenario = InvestmentScenario(
        user_id="demo",
        scenario_id="scenario-1",
        name="Research basket",
        reporting_currency="CNY",
        starting_cash=(
            {"amount": starting_cash, "currency": "CNY"}
            if starting_cash is not None
            else None
        ),
        created_at=NOW,
        updated_at=NOW,
    )
    return InvestmentScenarioDetail(
        scenario=scenario,
        positions=[
            ScenarioPosition(
                user_id="demo",
                scenario_id="scenario-1",
                symbol=symbol,
                asset_type="equity",
                quantity=quantity,
                created_at=NOW,
                updated_at=NOW,
            )
            for symbol, quantity in positions
        ],
    )


def _service(detail, market, exchange=None):
    return InvestmentResearchService(
        market_data=market,
        exchange_rates=exchange or FakeExchangeRates(),
        watchlist_reader=lambda user_id, limit: [],
        watchlist_writer=lambda item: True,
        watchlist_deleter=lambda *args: True,
        scenario_reader=lambda user_id, limit: [detail.scenario],
        scenario_detail_reader=lambda user_id, scenario_id: (
            detail if user_id == "demo" and scenario_id == "scenario-1" else None
        ),
        scenario_writer=lambda scenario: True,
        scenario_position_writer=lambda *args: True,
        scenario_deleter=lambda *args: True,
        profile_reader=lambda user_id: UserProfile(user_id=user_id),
        concentration_threshold_percent=Decimal("80"),
        clock=lambda: NOW,
    )


def test_research_snapshot_shares_one_budget_and_discloses_retrieval_time():
    market = FakeMarketData([_quote("AAPL", "100", timestamp_basis="retrieval_time")])
    service = _service(_scenario([]), market)

    result = service.get_instrument_research(
        "demo",
        "aapl",
        asset_type="equity",
        date_from=date(2026, 6, 1),
        date_to=date(2026, 7, 19),
    )

    assert result.symbol == "AAPL"
    assert result.trade_actions_allowed is False
    assert len(result.evidence) == 3
    assert "retrieval" in " ".join(result.limitations).lower()
    assert {id(item[2]) for item in market.calls} == {id(market.budget)}


def test_empty_scenario_is_explicit_and_skips_market_data():
    market = FakeMarketData()
    service = _service(_scenario([]), market)

    result = service.value_scenario("demo", "scenario-1")

    assert result.status == "empty"
    assert result.reporting_total is None
    assert market.calls == []


def test_research_compares_same_range_benchmark_and_keeps_readiness_separate():
    market = FakeMarketData(
        [_quote("AAPL", "120")],
        histories={
            "AAPL": _history("AAPL", ["100", "110", "120"]),
            "SPY": _history("SPY", ["100", "102", "105"], asset_type="etf"),
        },
    )
    service = _service(_scenario([]), market)

    result = service.get_instrument_research(
        "demo",
        "AAPL",
        asset_type="equity",
        date_from=date(2026, 6, 1),
        date_to=date(2026, 7, 19),
        benchmark_symbol="SPY",
    )

    assert result.performance.period_return_percent == Decimal("20.00")
    assert result.benchmark.status == "available"
    assert result.benchmark.excess_period_return_percent == Decimal("15.00")
    assert result.readiness.status == "insufficient_data"
    assert "benchmark_history" in {item.kind for item in result.evidence}
    assert result.trade_actions_allowed is False


def test_complete_scenario_converts_currency_and_flags_overallocation():
    market = FakeMarketData([_quote("AAPL", "100", timestamp_basis="retrieval_time")])
    service = _service(_scenario([("AAPL", "2")], starting_cash="1000"), market)

    result = service.value_scenario("demo", "scenario-1")

    assert result.status == "complete"
    assert result.native_totals[0].amount == Decimal("200")
    assert result.reporting_total.amount == Decimal("1400")
    assert result.remaining_cash is None
    assert result.overallocated_amount.amount == Decimal("400")
    codes = {finding.code for finding in result.risk.findings}
    assert "scenario_overallocated" in codes
    assert "retrieval_timed_quote" in codes
    assert result.trade_actions_allowed is False


def test_partial_scenario_preserves_native_value_without_fabricating_total():
    market = FakeMarketData([_quote("AAPL", "100")])
    service = _service(
        _scenario([("AAPL", "1"), ("UNKNOWN", "1")]),
        market,
    )

    result = service.value_scenario("demo", "scenario-1")

    assert result.status == "partial"
    assert result.converted_subtotal.amount == Decimal("700")
    assert result.reporting_total is None
    assert result.remaining_cash is None
    assert "missing_quote" in {finding.code for finding in result.risk.findings}


def test_scenario_lookup_is_user_scoped():
    detail = _scenario([])
    service = _service(detail, FakeMarketData())

    try:
        service.get_scenario("other-user", "scenario-1")
    except LookupError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("cross-user scenario lookup must fail")
