"""Finance-facing aggregation of canonical Agent Run AI costs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.models.cost_explorer import (
    AICostBreakdownItem,
    AICostBreakdowns,
    AICostBudget,
    AICostCoverage,
    AICostItem,
    AICostOverview,
    AICostPeriod,
    AICostSummary,
    AICostTrendPoint,
)
from app.models.costing import (
    CostIssue,
    ExchangeRateSnapshot,
    MoneyAmount,
    normalize_currency,
)
from app.models.runtime import AgentRunRecord
from app.runtime.costing.service import MONEY_QUANTUM, identity_exchange_rate


RecordsReader = Callable[..., list[dict[str, Any]]]
ExchangeRateLookup = Callable[[str, str, date], ExchangeRateSnapshot | None]
SHARE_QUANTUM = Decimal("0.1")
MAX_OVERVIEW_ITEMS = 200


def _money(amount: Decimal, currency: str) -> MoneyAmount:
    return MoneyAmount(
        amount=amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP),
        currency=currency,
    )


def _append_issue(issues: list[CostIssue], issue: CostIssue) -> None:
    if issue not in issues:
        issues.append(issue)


class AICostAnalyticsService:
    def __init__(
        self,
        *,
        records_reader: RecordsReader,
        exchange_rate_lookup: ExchangeRateLookup,
    ) -> None:
        self.records_reader = records_reader
        self.exchange_rate_lookup = exchange_rate_lookup

    def _convert(
        self,
        amount: MoneyAmount,
        reporting_currency: str,
        accounting_date: date,
    ) -> tuple[MoneyAmount | None, ExchangeRateSnapshot | None]:
        snapshot = identity_exchange_rate(
            amount.currency, reporting_currency, accounting_date
        )
        if snapshot is None:
            snapshot = self.exchange_rate_lookup(
                amount.currency, reporting_currency, accounting_date
            )
        if snapshot is None:
            return None, None
        return (
            _money(amount.amount * snapshot.exchange_rate, reporting_currency),
            snapshot,
        )

    def overview(
        self,
        *,
        user_id: str,
        date_from: date,
        date_to: date,
        reporting_currency: str,
        monthly_budget: MoneyAmount | dict[str, Any] | None = None,
    ) -> AICostOverview:
        reporting = normalize_currency(reporting_currency)
        parsed_budget = (
            MoneyAmount.model_validate(monthly_budget)
            if monthly_budget is not None
            else None
        )
        source_rows = self.records_reader(
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            limit=5000,
        )
        items: list[AICostItem] = []
        issues: list[CostIssue] = []
        providers: set[str] = set()
        stage_amounts: dict[str, dict[str, Decimal]] = {
            "provider": defaultdict(Decimal),
            "model": defaultdict(Decimal),
        }
        stage_runs: dict[str, dict[str, set[str]]] = {
            "provider": defaultdict(set),
            "model": defaultdict(set),
        }
        entrypoint_amounts: defaultdict[str, Decimal] = defaultdict(Decimal)
        entrypoint_runs: defaultdict[str, set[str]] = defaultdict(set)
        accepted_run_count = 0

        for row in source_rows:
            record = AgentRunRecord.model_validate(row["record"])
            occurred_at = row["created_at"]
            if isinstance(occurred_at, str):
                occurred_at = datetime.fromisoformat(occurred_at)
            if (
                record.user_id != user_id
                or occurred_at.date() < date_from
                or occurred_at.date() > date_to
            ):
                continue
            accepted_run_count += 1
            run_issues = [
                issue
                for issue in record.cost.issues
                if issue != "missing_exchange_rate"
            ]
            if not record.cost.billing_totals and not run_issues:
                continue

            converted_total = Decimal("0")
            snapshots: list[ExchangeRateSnapshot] = []
            for native_total in record.cost.billing_totals:
                converted, snapshot = self._convert(
                    native_total, reporting, occurred_at.date()
                )
                if converted is None:
                    _append_issue(run_issues, "missing_exchange_rate")
                    continue
                converted_total += converted.amount
                if snapshot and snapshot.exchange_rate_source != "identity":
                    snapshot_key = snapshot.model_dump(mode="json")
                    if all(
                        existing.model_dump(mode="json") != snapshot_key
                        for existing in snapshots
                    ):
                        snapshots.append(snapshot)

            item_status = "partial" if run_issues else "complete"
            reporting_total = (
                _money(converted_total, reporting)
                if item_status == "complete" and record.cost.billing_totals
                else None
            )
            run_providers = sorted(
                {stage.provider for stage in record.cost.stages if stage.provider}
            )
            run_models = sorted(
                {stage.model_name for stage in record.cost.stages if stage.model_name}
            )
            providers.update(run_providers)
            item = AICostItem(
                request_id=record.request_id,
                occurred_at=occurred_at,
                entrypoint=record.entrypoint,
                providers=run_providers,
                models=run_models,
                status=item_status,
                issues=run_issues,
                billing_totals=record.cost.billing_totals,
                reporting_total=reporting_total,
                exchange_rate_snapshots=snapshots,
            )
            items.append(item)
            for issue in run_issues:
                _append_issue(issues, issue)

            if item_status != "complete" or reporting_total is None:
                continue
            entrypoint_amounts[record.entrypoint] += reporting_total.amount
            entrypoint_runs[record.entrypoint].add(record.request_id)
            for stage in record.cost.stages:
                if stage.billing_total is None:
                    continue
                converted_stage, _ = self._convert(
                    stage.billing_total, reporting, occurred_at.date()
                )
                if converted_stage is None:
                    continue
                if stage.provider:
                    stage_amounts["provider"][stage.provider] += converted_stage.amount
                    stage_runs["provider"][stage.provider].add(record.request_id)
                if stage.model_name:
                    stage_amounts["model"][stage.model_name] += converted_stage.amount
                    stage_runs["model"][stage.model_name].add(record.request_id)

        items.sort(key=lambda item: item.occurred_at, reverse=True)
        partial_count = sum(item.status == "partial" for item in items)
        complete_count = len(items) - partial_count
        if not items:
            status = "empty"
        elif partial_count:
            status = "partial"
        else:
            status = "complete"

        converted_subtotal_amount = sum(
            (
                item.reporting_total.amount
                for item in items
                if item.reporting_total is not None
            ),
            Decimal("0"),
        )
        converted_subtotal = (
            _money(converted_subtotal_amount, reporting)
            if converted_subtotal_amount > 0
            else None
        )
        tracked_total = converted_subtotal if status == "complete" else None
        summary = AICostSummary(
            tracked_total=tracked_total,
            api_usage_total=tracked_total,
            converted_subtotal=converted_subtotal,
            subscription_total=None,
            budget=self._budget(
                tracked_total=tracked_total,
                monthly_budget=parsed_budget,
                reporting_currency=reporting,
                accounting_date=date_to,
                period_is_month_to_date=(
                    date_from.day == 1
                    and date_from.year == date_to.year
                    and date_from.month == date_to.month
                ),
            ),
        )

        trend = self._trend(items, reporting)
        breakdowns = AICostBreakdowns()
        if status == "complete" and tracked_total is not None:
            breakdowns = AICostBreakdowns(
                providers=self._breakdown(
                    stage_amounts["provider"],
                    stage_runs["provider"],
                    tracked_total.amount,
                    reporting,
                ),
                models=self._breakdown(
                    stage_amounts["model"],
                    stage_runs["model"],
                    tracked_total.amount,
                    reporting,
                ),
                entrypoints=self._breakdown(
                    entrypoint_amounts,
                    entrypoint_runs,
                    tracked_total.amount,
                    reporting,
                ),
            )

        fx_dates = [
            snapshot.exchange_rate_date
            for item in items
            for snapshot in item.exchange_rate_snapshots
        ]
        return AICostOverview(
            user_id=user_id,
            period=AICostPeriod(date_from=date_from, date_to=date_to),
            status=status,
            issues=issues,
            reporting_currency=reporting,
            coverage=AICostCoverage(
                run_count=accepted_run_count,
                billable_run_count=len(items),
                complete_run_count=complete_count,
                partial_run_count=partial_count,
                provider_count=len(providers),
                latest_exchange_rate_date=max(fx_dates) if fx_dates else None,
            ),
            summary=summary,
            trend=trend,
            breakdowns=breakdowns,
            items=items[:MAX_OVERVIEW_ITEMS],
        )

    def _budget(
        self,
        *,
        tracked_total: MoneyAmount | None,
        monthly_budget: MoneyAmount | None,
        reporting_currency: str,
        accounting_date: date,
        period_is_month_to_date: bool,
    ) -> AICostBudget:
        if monthly_budget is None:
            return AICostBudget(status="not_configured")
        converted_budget, _ = self._convert(
            monthly_budget, reporting_currency, accounting_date
        )
        if (
            tracked_total is None
            or converted_budget is None
            or not period_is_month_to_date
        ):
            return AICostBudget(status="unavailable", limit=converted_budget)
        if converted_budget.amount == 0:
            return AICostBudget(
                status="over_budget" if tracked_total.amount > 0 else "on_track",
                limit=converted_budget,
            )
        utilization = (
            tracked_total.amount / converted_budget.amount * Decimal("100")
        ).quantize(SHARE_QUANTUM, rounding=ROUND_HALF_UP)
        status = "on_track"
        if utilization >= 100:
            status = "over_budget"
        elif utilization >= 80:
            status = "watch"
        return AICostBudget(
            status=status,
            limit=converted_budget,
            utilization_percent=utilization,
        )

    @staticmethod
    def _trend(
        items: list[AICostItem], reporting_currency: str
    ) -> list[AICostTrendPoint]:
        grouped: dict[date, list[AICostItem]] = defaultdict(list)
        for item in items:
            grouped[item.occurred_at.date()].append(item)
        points = []
        for day in sorted(grouped):
            day_items = grouped[day]
            partial = any(item.status == "partial" for item in day_items)
            amount = sum(
                (
                    item.reporting_total.amount
                    for item in day_items
                    if item.reporting_total is not None
                ),
                Decimal("0"),
            )
            points.append(
                AICostTrendPoint(
                    date=day,
                    status="partial" if partial else "complete",
                    reporting_total=(
                        None if partial else _money(amount, reporting_currency)
                    ),
                    run_count=len(day_items),
                )
            )
        return points

    @staticmethod
    def _breakdown(
        amounts: dict[str, Decimal],
        runs: dict[str, set[str]],
        total: Decimal,
        currency: str,
    ) -> list[AICostBreakdownItem]:
        if total <= 0:
            return []
        result = []
        for key, amount in sorted(
            amounts.items(), key=lambda item: item[1], reverse=True
        ):
            result.append(
                AICostBreakdownItem(
                    key=key,
                    label=key,
                    reporting_total=_money(amount, currency),
                    share_percent=(amount / total * Decimal("100")).quantize(
                        SHARE_QUANTUM, rounding=ROUND_HALF_UP
                    ),
                    run_count=len(runs[key]),
                )
            )
        return result
