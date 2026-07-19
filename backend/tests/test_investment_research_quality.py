from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models.costing import MoneyAmount
from app.models.market_data import (
    ExternalCallUsage,
    MarketCacheMetadata,
    MarketPriceBar,
    MarketPriceHistory,
)
from app.models.user import AssetSnapshot, CostReportingPreferences, UserProfile
from app.runtime.policy.investment_readiness import evaluate_investment_readiness
from app.services.investment_metrics import calculate_historical_performance


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


def _history(prices: list[str]) -> MarketPriceHistory:
    bars = []
    for index, price in enumerate(prices):
        amount = MoneyAmount(amount=price, currency="USD")
        bars.append(
            MarketPriceBar(
                symbol="AAPL",
                asset_type="equity",
                period=date(2026, 7, 1) + timedelta(days=index),
                open=amount,
                high=amount,
                low=amount,
                close=amount,
                source="test",
            )
        )
    return MarketPriceHistory(
        symbol="AAPL",
        asset_type="equity",
        provider="test",
        currency="USD",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        fetched_at=NOW,
        bars=bars,
        cache=MarketCacheMetadata(
            cache_hit=False,
            cache_key="history-quality-test-key-0001",
            provider="test",
            fetched_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
        external_calls=ExternalCallUsage(budget=4, used=1, remaining=3),
    )


def _profile(**overrides) -> UserProfile:
    values = {
        "user_id": "demo",
        "monthly_income": 10_000,
        "monthly_expenses": 5_000,
        "assets": AssetSnapshot(
            cash_balance=10_000,
            savings=10_000,
            investments=0,
            liabilities=0,
        ),
        "cost_preferences": CostReportingPreferences(reporting_currency="CNY"),
    }
    values.update(overrides)
    return UserProfile(**values)


def test_performance_metrics_are_reproducible_from_daily_closes():
    result = calculate_historical_performance(_history(["100", "110", "99"]))

    assert result.status == "available"
    assert result.observation_count == 3
    assert result.period_return_percent == Decimal("-1.00")
    assert result.annualized_volatility_percent == Decimal("224.50")
    assert result.max_drawdown_percent == Decimal("10.00")


def test_performance_does_not_treat_missing_history_as_zero_return():
    result = calculate_historical_performance(_history(["100"]))

    assert result.status == "insufficient_data"
    assert result.period_return_percent is None
    assert result.annualized_volatility_percent is None
    assert result.max_drawdown_percent is None


def test_readiness_is_ready_with_positive_cash_flow_and_three_month_reserve():
    result = evaluate_investment_readiness(_profile())

    assert result.status == "ready"
    assert result.monthly_cash_flow == Decimal("5000.0")
    assert result.reserve_months == Decimal("4.00")
    assert result.trade_actions_allowed is False


def test_readiness_is_caution_for_negative_cash_flow_and_low_reserve():
    result = evaluate_investment_readiness(
        _profile(
            monthly_income=4_000,
            monthly_expenses=5_000,
            assets=AssetSnapshot(cash_balance=1_000, savings=1_000),
        )
    )

    assert result.status == "caution"
    assert result.monthly_cash_flow == Decimal("-1000.0")
    assert result.reserve_months == Decimal("0.40")
    assert {item.code for item in result.findings} == {
        "negative_monthly_cash_flow",
        "low_liquid_reserve",
    }


def test_readiness_is_insufficient_when_profile_baseline_is_missing():
    result = evaluate_investment_readiness(
        _profile(monthly_income=0, monthly_expenses=0)
    )

    assert result.status == "insufficient_data"
    assert result.monthly_cash_flow is None
    assert result.reserve_months is None
    assert {item.code for item in result.findings} == {
        "missing_monthly_income",
        "missing_monthly_expenses",
    }


def test_liabilities_are_disclosed_without_claiming_high_interest_debt():
    result = evaluate_investment_readiness(
        _profile(
            assets=AssetSnapshot(
                cash_balance=10_000,
                savings=10_000,
                liabilities=100_000,
            )
        )
    )

    assert result.status == "ready"
    finding = next(item for item in result.findings if item.code == "liabilities_present")
    assert finding.severity == "info"
    assert "interest rates" in finding.detail
    assert "high-interest" not in finding.detail
