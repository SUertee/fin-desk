"""Read-only instrument research and hypothetical scenario valuation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from app.connectors.exchange_rates.errors import ExchangeRateError
from app.connectors.market_data.errors import MarketDataError
from app.models.costing import MoneyAmount
from app.models.investment_research import (
    BenchmarkComparison,
    InstrumentResearchSnapshot,
    InvestmentScenario,
    InvestmentScenarioDetail,
    InvestmentScenarioRequest,
    InvestmentScenarioValuation,
    ResearchEvidenceSource,
    ScenarioCoverage,
    ScenarioPositionRequest,
    ScenarioPositionValuation,
    WatchlistItem,
    WatchlistItemRequest,
)
from app.models.investments import (
    InvestmentRiskFinding,
    PositionValuation,
    normalize_symbol,
)
from app.models.market_data import MarketAssetType
from app.models.user import UserProfile
from app.runtime.policy.investment_readiness import evaluate_investment_readiness
from app.runtime.policy.investment_policy import evaluate_investment_risk
from app.services.exchange_rates import ExchangeRateService
from app.services.investment_metrics import calculate_historical_performance
from app.services.market_data import MarketDataService


WatchlistReader = Callable[[str, int], list[WatchlistItem]]
WatchlistWriter = Callable[[WatchlistItem], bool]
WatchlistDeleter = Callable[[str, str, MarketAssetType], bool]
ScenarioReader = Callable[[str, int], list[InvestmentScenario]]
ScenarioDetailReader = Callable[[str, str], InvestmentScenarioDetail | None]
ScenarioWriter = Callable[[InvestmentScenario], bool]
ScenarioPositionWriter = Callable[[str, str, list[ScenarioPositionRequest]], bool]
ScenarioDeleter = Callable[[str, str], bool]
ProfileReader = Callable[[str], UserProfile]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InvestmentResearchService:
    def __init__(
        self,
        *,
        market_data: MarketDataService,
        exchange_rates: ExchangeRateService,
        watchlist_reader: WatchlistReader,
        watchlist_writer: WatchlistWriter,
        watchlist_deleter: WatchlistDeleter,
        scenario_reader: ScenarioReader,
        scenario_detail_reader: ScenarioDetailReader,
        scenario_writer: ScenarioWriter,
        scenario_position_writer: ScenarioPositionWriter,
        scenario_deleter: ScenarioDeleter,
        profile_reader: ProfileReader,
        stale_after_days: int = 3,
        concentration_threshold_percent: Decimal = Decimal("35"),
        clock: Clock = _utc_now,
    ) -> None:
        self.market_data = market_data
        self.exchange_rates = exchange_rates
        self.watchlist_reader = watchlist_reader
        self.watchlist_writer = watchlist_writer
        self.watchlist_deleter = watchlist_deleter
        self.scenario_reader = scenario_reader
        self.scenario_detail_reader = scenario_detail_reader
        self.scenario_writer = scenario_writer
        self.scenario_position_writer = scenario_position_writer
        self.scenario_deleter = scenario_deleter
        self.profile_reader = profile_reader
        self.stale_after_days = stale_after_days
        self.concentration_threshold_percent = concentration_threshold_percent
        self.clock = clock

    def list_watchlist(self, user_id: str) -> list[WatchlistItem]:
        return self.watchlist_reader(user_id, 100)

    def follow(self, user_id: str, request: WatchlistItemRequest) -> WatchlistItem:
        now = self.clock()
        item = WatchlistItem(
            user_id=user_id,
            symbol=request.symbol,
            asset_type=request.asset_type,
            note=request.note,
            created_at=now,
            updated_at=now,
        )
        if not self.watchlist_writer(item):
            raise RuntimeError("watchlist item could not be persisted")
        return item

    def unfollow(
        self,
        user_id: str,
        symbol: str,
        asset_type: MarketAssetType,
    ) -> None:
        if not self.watchlist_deleter(user_id, symbol, asset_type):
            raise RuntimeError("watchlist item could not be deleted")

    def list_scenarios(self, user_id: str) -> list[InvestmentScenario]:
        return self.scenario_reader(user_id, 50)

    def create_scenario(
        self,
        user_id: str,
        request: InvestmentScenarioRequest,
    ) -> InvestmentScenario:
        now = self.clock()
        scenario = InvestmentScenario(
            user_id=user_id,
            name=request.name,
            reporting_currency=request.reporting_currency,
            starting_cash=(
                MoneyAmount(
                    amount=request.starting_cash_amount,
                    currency=request.reporting_currency,
                )
                if request.starting_cash_amount is not None
                else None
            ),
            created_at=now,
            updated_at=now,
        )
        if not self.scenario_writer(scenario):
            raise RuntimeError("investment scenario could not be persisted")
        return scenario

    def get_scenario(self, user_id: str, scenario_id: str) -> InvestmentScenarioDetail:
        detail = self.scenario_detail_reader(user_id, scenario_id)
        if detail is None:
            raise LookupError("investment scenario not found")
        return detail

    def replace_positions(
        self,
        user_id: str,
        scenario_id: str,
        positions: list[ScenarioPositionRequest],
    ) -> InvestmentScenarioDetail:
        if not self.scenario_position_writer(user_id, scenario_id, positions):
            raise LookupError("investment scenario not found or positions were not saved")
        return self.get_scenario(user_id, scenario_id)

    def delete_scenario(self, user_id: str, scenario_id: str) -> None:
        if self.scenario_detail_reader(user_id, scenario_id) is None:
            raise LookupError("investment scenario not found")
        if not self.scenario_deleter(user_id, scenario_id):
            raise RuntimeError("investment scenario could not be deleted")

    def get_instrument_research(
        self,
        user_id: str,
        symbol: str,
        *,
        asset_type: MarketAssetType,
        date_from: date,
        date_to: date,
        benchmark_symbol: str = "SPY",
    ) -> InstrumentResearchSnapshot:
        budget = self.market_data.new_budget()
        profile = self.market_data.get_profile(
            symbol,
            asset_type=asset_type,
            budget=budget,
        )
        quote_result = self.market_data.get_quotes(
            [profile.symbol],
            asset_type=asset_type,
            budget=budget,
        )
        history = self.market_data.get_history(
            profile.symbol,
            asset_type=asset_type,
            date_from=date_from,
            date_to=date_to,
            budget=budget,
        )
        quote = next(
            (item for item in quote_result.quotes if item.symbol == profile.symbol),
            None,
        )
        performance = calculate_historical_performance(history)
        normalized_benchmark = normalize_symbol(benchmark_symbol)
        benchmark = BenchmarkComparison(
            status="insufficient_data",
            benchmark_symbol=normalized_benchmark,
            limitation="Instrument history is insufficient for a benchmark comparison.",
        )
        followed = any(
            item.symbol == profile.symbol and item.asset_type == asset_type
            for item in self.list_watchlist(user_id)
        )
        evidence = [
            ResearchEvidenceSource(
                kind="profile",
                source=profile.source,
                as_of=profile.fetched_at,
                description="Normalized instrument profile",
            ),
            ResearchEvidenceSource(
                kind="history",
                source=history.provider,
                as_of=history.fetched_at,
                description=f"Daily price history from {date_from} to {date_to}",
            ),
        ]
        limitations = [
            "Research is read-only and does not place or simulate brokerage orders."
        ]
        if performance.status == "available":
            try:
                benchmark_history = (
                    history
                    if normalized_benchmark == history.symbol
                    else self.market_data.get_history(
                        normalized_benchmark,
                        asset_type="etf",
                        date_from=date_from,
                        date_to=date_to,
                        budget=budget,
                    )
                )
                benchmark_performance = calculate_historical_performance(
                    benchmark_history
                )
                if benchmark_performance.status == "available":
                    benchmark = BenchmarkComparison(
                        status="available",
                        benchmark_symbol=normalized_benchmark,
                        performance=benchmark_performance,
                        excess_period_return_percent=(
                            performance.period_return_percent
                            - benchmark_performance.period_return_percent
                        ).quantize(Decimal("0.01")),
                    )
                else:
                    benchmark = BenchmarkComparison(
                        status="insufficient_data",
                        benchmark_symbol=normalized_benchmark,
                        performance=benchmark_performance,
                        limitation="Benchmark history is insufficient for comparison.",
                    )
                evidence.append(
                    ResearchEvidenceSource(
                        kind="benchmark_history",
                        source=benchmark_history.provider,
                        as_of=benchmark_history.fetched_at,
                        description=(
                            f"{normalized_benchmark} benchmark history from "
                            f"{date_from} to {date_to}"
                        ),
                    )
                )
            except MarketDataError:
                benchmark = BenchmarkComparison(
                    status="unavailable",
                    benchmark_symbol=normalized_benchmark,
                    limitation="Benchmark evidence is currently unavailable.",
                )
                limitations.append(
                    f"{normalized_benchmark} benchmark evidence is currently unavailable."
                )
        if quote is not None:
            evidence.append(
                ResearchEvidenceSource(
                    kind="quote",
                    source=quote.source,
                    as_of=quote.quote_as_of,
                    description="Latest normalized market quote",
                )
            )
            if quote.timestamp_basis == "retrieval_time":
                limitations.append(
                    "The quote time records retrieval because the provider did not expose an exchange timestamp."
                )
            if self.clock() - quote.quote_as_of > timedelta(
                days=self.stale_after_days
            ):
                limitations.append(
                    f"The latest quote is older than the {self.stale_after_days}-day freshness threshold."
                )
        else:
            limitations.append("No current quote was returned for this instrument.")
        return InstrumentResearchSnapshot(
            user_id=user_id,
            symbol=profile.symbol,
            asset_type=asset_type,
            followed=followed,
            profile=profile,
            quote=quote,
            history=history,
            performance=performance,
            benchmark=benchmark,
            readiness=evaluate_investment_readiness(self.profile_reader(user_id)),
            evidence=evidence,
            limitations=limitations,
        )

    def value_scenario(
        self,
        user_id: str,
        scenario_id: str,
        *,
        as_of: datetime | None = None,
    ) -> InvestmentScenarioValuation:
        selected_time = as_of or self.clock()
        detail = self.get_scenario(user_id, scenario_id)
        scenario = detail.scenario
        readiness = evaluate_investment_readiness(self.profile_reader(user_id))
        if not detail.positions:
            return InvestmentScenarioValuation(
                status="empty",
                scenario=scenario,
                as_of=selected_time,
                readiness=readiness,
                limitations=[
                    "Add hypothetical positions to calculate a research scenario."
                ],
            )

        budget = self.market_data.new_budget()
        quote_map = {}
        quote_sources: set[str] = set()
        for asset_type in sorted({item.asset_type for item in detail.positions}):
            symbols = [
                item.symbol for item in detail.positions if item.asset_type == asset_type
            ]
            result = self.market_data.get_quotes(
                symbols,
                asset_type=asset_type,
                budget=budget,
            )
            for quote in result.quotes:
                quote_map[(quote.symbol, quote.asset_type)] = quote
                quote_sources.add(quote.source)

        valuations = [
            self._value_scenario_position(
                position,
                quote_map.get((position.symbol, position.asset_type)),
                reporting_currency=scenario.reporting_currency,
            )
            for position in detail.positions
        ]
        native_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        reporting_subtotal = Decimal("0")
        for valuation in valuations:
            if valuation.native_market_value:
                native_totals[valuation.native_market_value.currency] += (
                    valuation.native_market_value.amount
                )
            if valuation.reporting_market_value:
                reporting_subtotal += valuation.reporting_market_value.amount

        is_complete = all(item.reporting_market_value is not None for item in valuations)
        converted = (
            MoneyAmount(
                amount=reporting_subtotal,
                currency=scenario.reporting_currency,
            )
            if any(item.reporting_market_value for item in valuations)
            else None
        )
        reporting_total = converted if is_complete else None
        remaining_cash = None
        overallocated_amount = None
        risk_positions = [
            PositionValuation(
                account_id=scenario.scenario_id,
                **item.model_dump(exclude={"issues"}),
                issues=list(item.issues),
            )
            for item in valuations
        ]
        risk = evaluate_investment_risk(
            accounts=[],
            positions=risk_positions,
            as_of=selected_time,
            stale_after_days=self.stale_after_days,
            concentration_threshold_percent=self.concentration_threshold_percent,
        )
        if scenario.starting_cash and reporting_total:
            difference = scenario.starting_cash.amount - reporting_total.amount
            if difference >= 0:
                remaining_cash = MoneyAmount(
                    amount=difference,
                    currency=scenario.reporting_currency,
                )
            else:
                overallocated_amount = MoneyAmount(
                    amount=-difference,
                    currency=scenario.reporting_currency,
                )
                risk.findings.append(
                    InvestmentRiskFinding(
                        code="scenario_overallocated",
                        severity="high",
                        title="Scenario exceeds starting cash",
                        detail="Hypothetical position value is greater than the configured scenario budget.",
                        symbols=[item.symbol for item in valuations],
                    )
                )

        limitations = [
            "This is a hypothetical research scenario, not an account balance or order recommendation."
        ]
        if not is_complete:
            limitations.append(
                "The scenario total is incomplete because at least one quote or exchange rate is unavailable."
            )
        return InvestmentScenarioValuation(
            status="complete" if is_complete else "partial",
            scenario=scenario,
            as_of=selected_time,
            positions=valuations,
            native_totals=[
                MoneyAmount(amount=amount, currency=currency)
                for currency, amount in sorted(native_totals.items())
            ],
            converted_subtotal=converted,
            reporting_total=reporting_total,
            remaining_cash=remaining_cash,
            overallocated_amount=overallocated_amount,
            coverage=ScenarioCoverage(
                position_count=len(valuations),
                quoted_position_count=sum(item.quote is not None for item in valuations),
                reporting_position_count=sum(
                    item.reporting_market_value is not None for item in valuations
                ),
                quote_sources=sorted(quote_sources),
            ),
            risk=risk,
            readiness=readiness,
            limitations=limitations,
        )

    def _value_scenario_position(
        self,
        position,
        quote,
        *,
        reporting_currency: str,
    ) -> ScenarioPositionValuation:
        if quote is None:
            return ScenarioPositionValuation(
                symbol=position.symbol,
                asset_type=position.asset_type,
                quantity=position.quantity,
                issues=["missing_quote"],
            )
        native = MoneyAmount(
            amount=position.quantity * quote.price.amount,
            currency=quote.price.currency,
        )
        try:
            exchange_rate = self.exchange_rates.get_rate(
                quote.price.currency,
                reporting_currency,
                on_date=quote.quote_as_of.date(),
            )
        except ExchangeRateError:
            exchange_rate = None
        if exchange_rate is None:
            return ScenarioPositionValuation(
                symbol=position.symbol,
                asset_type=position.asset_type,
                quantity=position.quantity,
                quote=quote,
                native_market_value=native,
                issues=["missing_exchange_rate"],
            )
        return ScenarioPositionValuation(
            symbol=position.symbol,
            asset_type=position.asset_type,
            quantity=position.quantity,
            quote=quote,
            native_market_value=native,
            reporting_market_value=MoneyAmount(
                amount=native.amount * exchange_rate.exchange_rate,
                currency=reporting_currency,
            ),
            exchange_rate_snapshot=exchange_rate,
        )
