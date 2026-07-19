"""Pure historical investment metrics over normalized daily price history."""

from __future__ import annotations

from decimal import Decimal, localcontext

from app.models.investment_research import HistoricalPerformanceSummary
from app.models.market_data import MarketPriceHistory


PERCENT = Decimal("100")
TRADING_DAYS = Decimal("252")
PERCENT_QUANTUM = Decimal("0.01")


def _round_percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM)


def calculate_historical_performance(
    history: MarketPriceHistory,
) -> HistoricalPerformanceSummary:
    """Calculate reproducible metrics without provider- or LLM-specific behavior."""

    ordered = sorted(history.bars, key=lambda item: item.period)
    if len(ordered) < 2:
        return HistoricalPerformanceSummary(
            status="insufficient_data",
            symbol=history.symbol,
            currency=history.currency,
            observation_count=len(ordered),
            date_from=ordered[0].period if ordered else None,
            date_to=ordered[-1].period if ordered else None,
        )

    closes = [bar.close.amount for bar in ordered]
    period_return = (closes[-1] / closes[0] - Decimal("1")) * PERCENT

    peak = closes[0]
    max_drawdown = Decimal("0")
    for close in closes:
        peak = max(peak, close)
        drawdown = (peak - close) / peak * PERCENT
        max_drawdown = max(max_drawdown, drawdown)

    daily_returns = [
        closes[index] / closes[index - 1] - Decimal("1")
        for index in range(1, len(closes))
    ]
    annualized_volatility = None
    if len(daily_returns) >= 2:
        mean = sum(daily_returns, Decimal("0")) / Decimal(len(daily_returns))
        variance = sum(
            ((value - mean) ** 2 for value in daily_returns),
            Decimal("0"),
        ) / Decimal(len(daily_returns) - 1)
        with localcontext() as context:
            context.prec = 28
            annualized_volatility = variance.sqrt() * TRADING_DAYS.sqrt() * PERCENT

    return HistoricalPerformanceSummary(
        status="available",
        symbol=history.symbol,
        currency=history.currency,
        observation_count=len(ordered),
        date_from=ordered[0].period,
        date_to=ordered[-1].period,
        period_return_percent=_round_percent(period_return),
        annualized_volatility_percent=(
            _round_percent(annualized_volatility)
            if annualized_volatility is not None
            else None
        ),
        max_drawdown_percent=_round_percent(max_drawdown),
    )
