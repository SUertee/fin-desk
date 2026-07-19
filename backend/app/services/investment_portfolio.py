"""Deterministic portfolio valuation over persisted holdings and market facts."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from app.connectors.market_data.provider import MarketDataProvider
from app.models.costing import ExchangeRateSnapshot, MoneyAmount, normalize_currency
from app.models.investments import (
    InvestmentAccount,
    InvestmentPosition,
    MarketQuote,
    PortfolioCoverage,
    PortfolioSnapshot,
    PositionValuation,
)
from app.runtime.policy.investment_policy import evaluate_investment_risk


AccountReader = Callable[[str, int], list[InvestmentAccount]]
PositionReader = Callable[[str, int], list[InvestmentPosition]]
ExchangeRateLookup = Callable[[str, str, date], ExchangeRateSnapshot | None]


class PortfolioService:
    def __init__(
        self,
        *,
        account_reader: AccountReader,
        position_reader: PositionReader,
        market_data_provider: MarketDataProvider,
        exchange_rate_lookup: ExchangeRateLookup,
        stale_after_days: int = 3,
        concentration_threshold_percent: Decimal = Decimal("35"),
    ) -> None:
        self.account_reader = account_reader
        self.position_reader = position_reader
        self.market_data_provider = market_data_provider
        self.exchange_rate_lookup = exchange_rate_lookup
        self.stale_after_days = stale_after_days
        self.concentration_threshold_percent = concentration_threshold_percent

    def get_snapshot(
        self,
        user_id: str,
        *,
        as_of: datetime,
        reporting_currency: str,
    ) -> PortfolioSnapshot:
        reporting = normalize_currency(reporting_currency)
        accounts = self.account_reader(user_id, 50)
        positions = self.position_reader(user_id, 500)
        if not positions:
            return PortfolioSnapshot(
                user_id=user_id,
                status="empty",
                as_of=as_of,
                reporting_currency=reporting,
                accounts=accounts,
                coverage=PortfolioCoverage(account_count=len(accounts)),
                risk=evaluate_investment_risk(
                    accounts=accounts,
                    positions=[],
                    as_of=as_of,
                    stale_after_days=self.stale_after_days,
                    concentration_threshold_percent=self.concentration_threshold_percent,
                ),
            )

        instruments = list(dict.fromkeys(position.instrument for position in positions))
        quote_batch = self.market_data_provider.get_latest_quotes(
            instruments,
            as_of=as_of,
        )
        quote_map = {quote.instrument: quote for quote in quote_batch.quotes}
        valuations = [
            self._value_position(position, quote_map.get(position.instrument), reporting)
            for position in positions
        ]

        native = defaultdict(lambda: Decimal("0"))
        reporting_subtotal = Decimal("0")
        for valuation in valuations:
            if valuation.native_market_value:
                native[valuation.native_market_value.currency] += (
                    valuation.native_market_value.amount
                )
            if valuation.reporting_market_value:
                reporting_subtotal += valuation.reporting_market_value.amount

        is_complete = all(
            valuation.reporting_market_value is not None for valuation in valuations
        )
        latest_quote = max(
            (quote.quote_as_of for quote in quote_batch.quotes),
            default=None,
        )
        sources = sorted({quote.source for quote in quote_batch.quotes})
        risk = evaluate_investment_risk(
            accounts=accounts,
            positions=valuations,
            as_of=as_of,
            stale_after_days=self.stale_after_days,
            concentration_threshold_percent=self.concentration_threshold_percent,
        )
        return PortfolioSnapshot(
            user_id=user_id,
            status="complete" if is_complete else "partial",
            as_of=as_of,
            reporting_currency=reporting,
            accounts=accounts,
            positions=valuations,
            native_totals=[
                MoneyAmount(amount=amount, currency=currency)
                for currency, amount in sorted(native.items())
            ],
            converted_subtotal=(
                MoneyAmount(amount=reporting_subtotal, currency=reporting)
                if any(item.reporting_market_value for item in valuations)
                else None
            ),
            reporting_total=(
                MoneyAmount(amount=reporting_subtotal, currency=reporting)
                if is_complete
                else None
            ),
            coverage=PortfolioCoverage(
                account_count=len(accounts),
                position_count=len(positions),
                quoted_position_count=sum(item.quote is not None for item in valuations),
                reporting_position_count=sum(
                    item.reporting_market_value is not None for item in valuations
                ),
                quote_sources=sources,
                latest_quote_as_of=latest_quote,
            ),
            risk=risk,
        )

    def _value_position(
        self,
        position: InvestmentPosition,
        quote: MarketQuote | None,
        reporting_currency: str,
    ) -> PositionValuation:
        if quote is None:
            return PositionValuation(
                account_id=position.account_id,
                symbol=position.symbol,
                asset_type=position.asset_type,
                quantity=position.quantity,
                issues=["missing_quote"],
            )

        native = MoneyAmount(
            amount=position.quantity * quote.price.amount,
            currency=quote.price.currency,
        )
        issues = []
        if quote.price.currency == reporting_currency:
            reporting = MoneyAmount(amount=native.amount, currency=reporting_currency)
            exchange_rate = self.exchange_rate_lookup(
                reporting_currency,
                reporting_currency,
                quote.quote_as_of.date(),
            )
        else:
            exchange_rate = self.exchange_rate_lookup(
                quote.price.currency,
                reporting_currency,
                quote.quote_as_of.date(),
            )
            reporting = (
                MoneyAmount(
                    amount=native.amount * exchange_rate.exchange_rate,
                    currency=reporting_currency,
                )
                if exchange_rate is not None
                else None
            )
            if exchange_rate is None:
                issues.append("missing_exchange_rate")

        return PositionValuation(
            account_id=position.account_id,
            symbol=position.symbol,
            asset_type=position.asset_type,
            quantity=position.quantity,
            quote=quote,
            native_market_value=native,
            reporting_market_value=reporting,
            exchange_rate_snapshot=exchange_rate,
            issues=issues,
        )
