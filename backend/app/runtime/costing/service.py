"""Profile-aware native and reporting-currency LLM cost calculation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

from app.config.settings import ModelProfile, load_model_profiles
from app.models.costing import (
    AgentRunCost,
    CostIssue,
    ExchangeRateSnapshot,
    LLMStageCost,
    ModelPricing,
    MoneyAmount,
    normalize_currency,
)
from app.models.runtime_usage import AgentRunUsage


MONEY_QUANTUM = Decimal("0.000000000001")
ExchangeRateLookup = Callable[[str, str, date], ExchangeRateSnapshot | None]


def _money(value: Decimal, currency: str) -> MoneyAmount:
    return MoneyAmount(
        amount=value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP),
        currency=currency,
    )


def identity_exchange_rate(
    billing_currency: str,
    reporting_currency: str,
    accounting_date: date,
) -> ExchangeRateSnapshot | None:
    billing = normalize_currency(billing_currency)
    reporting = normalize_currency(reporting_currency)
    if billing != reporting:
        return None
    return ExchangeRateSnapshot(
        billing_currency=billing,
        reporting_currency=reporting,
        exchange_rate=Decimal("1"),
        exchange_rate_date=accounting_date,
        exchange_rate_source="identity",
    )


class CostingService:
    def __init__(
        self,
        *,
        exchange_rate_lookup: ExchangeRateLookup | None = None,
        profiles: dict[str, ModelProfile] | None = None,
    ) -> None:
        self.exchange_rate_lookup = exchange_rate_lookup
        self.profiles = profiles

    def _profiles(self) -> dict[str, ModelProfile]:
        return self.profiles if self.profiles is not None else load_model_profiles()

    def _pricing(
        self,
        *,
        profile_name: str,
        observed_model_name: str | None,
    ) -> ModelPricing | None:
        profile = self._profiles().get(profile_name)
        if profile is None:
            return None
        if observed_model_name and observed_model_name != profile.model:
            return None
        if (
            profile.input_cost_per_1m is None
            or profile.output_cost_per_1m is None
            or profile.pricing_effective_date is None
        ):
            return None
        return ModelPricing(
            profile=profile.name,
            provider=profile.provider,
            model_name=profile.model,
            billing_currency=profile.billing_currency,
            input_cost_per_1m=profile.input_cost_per_1m,
            cached_input_cost_per_1m=profile.cached_input_cost_per_1m,
            output_cost_per_1m=profile.output_cost_per_1m,
            pricing_source=profile.pricing_source,
            pricing_effective_date=profile.pricing_effective_date,
        )

    def _exchange_rate(
        self,
        billing_currency: str,
        reporting_currency: str,
        accounting_date: date,
    ) -> ExchangeRateSnapshot | None:
        identity = identity_exchange_rate(
            billing_currency,
            reporting_currency,
            accounting_date,
        )
        if identity is not None:
            return identity
        if self.exchange_rate_lookup is None:
            return None
        return self.exchange_rate_lookup(
            billing_currency,
            reporting_currency,
            accounting_date,
        )

    def stage_cost(
        self,
        *,
        stage: str,
        status: str,
        profile_name: str,
        model_name: str | None,
        usage: AgentRunUsage | dict | None,
        reporting_currency: str,
        accounting_date: date,
        _exchange_rate_cache: dict[
            tuple[str, str, date], ExchangeRateSnapshot | None
        ]
        | None = None,
    ) -> LLMStageCost:
        parsed_usage = AgentRunUsage.model_validate(usage or {})
        profile = self._profiles().get(profile_name)
        result = LLMStageCost(
            stage=stage,
            status=status,
            profile=profile_name,
            provider=profile.provider if profile else None,
            model_name=model_name or (profile.model if profile else None),
            usage=parsed_usage,
        )
        if parsed_usage.input_tokens + parsed_usage.output_tokens == 0:
            return result

        pricing = self._pricing(
            profile_name=profile_name,
            observed_model_name=model_name,
        )
        if pricing is None:
            result.issues = ["missing_pricing"]
            return result

        divisor = Decimal("1000000")
        cache_detail_complete = (
            pricing.cached_input_cost_per_1m is not None
            and parsed_usage.cached_input_tokens + parsed_usage.uncached_input_tokens
            == parsed_usage.input_tokens
        )
        if cache_detail_complete:
            cached_input_cost = (
                Decimal(parsed_usage.cached_input_tokens)
                * pricing.cached_input_cost_per_1m
                / divisor
            )
            uncached_input_cost = (
                Decimal(parsed_usage.uncached_input_tokens)
                * pricing.input_cost_per_1m
                / divisor
            )
            input_cost = cached_input_cost + uncached_input_cost
            result.input_pricing_basis = "cache_split"
            result.billing_cached_input_cost = _money(
                cached_input_cost,
                pricing.billing_currency,
            )
            result.billing_uncached_input_cost = _money(
                uncached_input_cost,
                pricing.billing_currency,
            )
        else:
            input_cost = (
                Decimal(parsed_usage.input_tokens)
                * pricing.input_cost_per_1m
                / divisor
            )
            result.input_pricing_basis = "standard_rate_fallback"
        output_cost = Decimal(parsed_usage.output_tokens) * pricing.output_cost_per_1m / divisor
        total_cost = input_cost + output_cost
        result.pricing = pricing
        result.provider = pricing.provider
        result.model_name = pricing.model_name
        result.billing_input_cost = _money(input_cost, pricing.billing_currency)
        result.billing_output_cost = _money(output_cost, pricing.billing_currency)
        result.billing_total = _money(total_cost, pricing.billing_currency)

        rate_key = (
            normalize_currency(pricing.billing_currency),
            normalize_currency(reporting_currency),
            accounting_date,
        )
        if _exchange_rate_cache is None:
            snapshot = self._exchange_rate(*rate_key)
        else:
            if rate_key not in _exchange_rate_cache:
                _exchange_rate_cache[rate_key] = self._exchange_rate(*rate_key)
            snapshot = _exchange_rate_cache[rate_key]
        if snapshot is None:
            result.issues = ["missing_exchange_rate"]
            return result
        result.exchange_rate_snapshot = snapshot
        result.reporting_total = _money(
            result.billing_total.amount * snapshot.exchange_rate,
            snapshot.reporting_currency,
        )
        return result

    def run_cost(
        self,
        *,
        stages: list[LLMStageCost],
        reporting_currency: str,
    ) -> AgentRunCost:
        reporting = normalize_currency(reporting_currency)
        billable = [
            stage
            for stage in stages
            if stage.usage.input_tokens + stage.usage.output_tokens > 0
        ]
        if not billable:
            return AgentRunCost(
                status="not_applicable",
                reporting_currency=reporting,
                stages=stages,
            )

        grouped: defaultdict[str, Decimal] = defaultdict(Decimal)
        issues: list[CostIssue] = []
        reporting_amount = Decimal("0")
        for stage in billable:
            for issue in stage.issues:
                if issue not in issues:
                    issues.append(issue)
            if stage.billing_total is not None:
                grouped[stage.billing_total.currency] += stage.billing_total.amount
            if stage.reporting_total is not None:
                reporting_amount += stage.reporting_total.amount

        billing_totals = [_money(grouped[currency], currency) for currency in sorted(grouped)]
        if issues:
            return AgentRunCost(
                status="partial",
                issues=issues,
                reporting_currency=reporting,
                billing_totals=billing_totals,
                reporting_total=None,
                stages=stages,
            )
        return AgentRunCost(
            status="complete",
            reporting_currency=reporting,
            billing_totals=billing_totals,
            reporting_total=_money(reporting_amount, reporting),
            stages=stages,
        )

    def cost_stage_entries(
        self,
        stage_entries: dict[str, dict],
        *,
        reporting_currency: str,
        accounting_date: date,
    ) -> AgentRunCost:
        stages = []
        exchange_rate_cache: dict[
            tuple[str, str, date], ExchangeRateSnapshot | None
        ] = {}
        for stage_name, entry in stage_entries.items():
            stages.append(
                self.stage_cost(
                    stage=stage_name,
                    status=str(entry.get("status") or "unknown"),
                    profile_name=str(entry.get("profile") or ""),
                    model_name=entry.get("model_name"),
                    usage={
                        "request_count": entry.get("request_count", 0),
                        "model_response_count": entry.get("model_response_count", 0),
                        "input_tokens": entry.get("input_tokens", 0),
                        "cached_input_tokens": entry.get("cached_input_tokens", 0),
                        "uncached_input_tokens": entry.get("uncached_input_tokens", 0),
                        "output_tokens": entry.get("output_tokens", 0),
                        "total_tokens": entry.get("total_tokens", 0),
                    },
                    reporting_currency=reporting_currency,
                    accounting_date=accounting_date,
                    _exchange_rate_cache=exchange_rate_cache,
                )
            )
        return self.run_cost(stages=stages, reporting_currency=reporting_currency)
