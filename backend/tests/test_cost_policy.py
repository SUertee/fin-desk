from datetime import date
from decimal import Decimal

from app.config.settings import CostSettings, ModelProfile
from app.models.costing import ExchangeRateSnapshot
from app.models.runtime import AgentRunUsage
from app.runtime.costing import CostingService


TODAY = date(2026, 7, 13)


def _profile(
    name: str,
    *,
    model: str,
    currency: str,
    input_rate: str,
    output_rate: str,
) -> ModelProfile:
    return ModelProfile(
        name=name,
        provider=f"{name}-provider",
        model=model,
        billing_currency=currency,
        input_cost_per_1m=Decimal(input_rate),
        output_cost_per_1m=Decimal(output_rate),
        pricing_source="test-price-list",
        pricing_effective_date=TODAY,
    )


def _usage(input_tokens: int, output_tokens: int) -> AgentRunUsage:
    return AgentRunUsage(
        request_count=1,
        model_response_count=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def test_stage_cost_uses_profile_native_currency_and_decimal_precision():
    profiles = {
        "router": _profile(
            "router",
            model="model-a",
            currency="USD",
            input_rate="0.07",
            output_rate="0.28",
        )
    }
    service = CostingService(profiles=profiles)

    stage = service.stage_cost(
        stage="route_classify",
        status="called",
        profile_name="router",
        model_name="model-a",
        usage=_usage(7, 3),
        reporting_currency="USD",
        accounting_date=TODAY,
    )

    assert stage.billing_total is not None
    assert stage.billing_total.currency == "USD"
    assert stage.billing_total.amount == Decimal("0.000001330000")
    assert stage.reporting_total == stage.billing_total
    assert stage.exchange_rate_snapshot.exchange_rate_source == "identity"


def test_model_override_does_not_inherit_profile_price():
    service = CostingService(
        profiles={
            "chat": _profile(
                "chat",
                model="deepseek-chat",
                currency="USD",
                input_rate="0.07",
                output_rate="0.28",
            )
        }
    )

    stage = service.stage_cost(
        stage="llm_compose",
        status="called",
        profile_name="chat",
        model_name="gpt-4o",
        usage=_usage(100, 50),
        reporting_currency="USD",
        accounting_date=TODAY,
    )

    assert stage.issues == ["missing_pricing"]
    assert stage.billing_total is None


def test_invalid_output_is_still_billed():
    service = CostingService(
        profiles={
            "router": _profile(
                "router",
                model="model-a",
                currency="USD",
                input_rate="1",
                output_rate="2",
            )
        }
    )

    stage = service.stage_cost(
        stage="route_classify",
        status="invalid_output",
        profile_name="router",
        model_name="model-a",
        usage=_usage(10, 5),
        reporting_currency="USD",
        accounting_date=TODAY,
    )

    assert stage.status == "invalid_output"
    assert stage.billing_total.amount == Decimal("0.000020000000")


def test_mixed_native_currencies_are_grouped_then_reported():
    profiles = {
        "router": _profile(
            "router",
            model="model-usd",
            currency="USD",
            input_rate="1",
            output_rate="1",
        ),
        "chat": _profile(
            "chat",
            model="model-cny",
            currency="CNY",
            input_rate="1",
            output_rate="1",
        ),
    }

    def lookup(billing: str, reporting: str, on_date: date):
        return ExchangeRateSnapshot(
            billing_currency=billing,
            reporting_currency=reporting,
            exchange_rate=Decimal("7.2"),
            exchange_rate_date=on_date,
            exchange_rate_source="test-fx",
        )

    service = CostingService(profiles=profiles, exchange_rate_lookup=lookup)
    stages = [
        service.stage_cost(
            stage="route_classify",
            status="called",
            profile_name="router",
            model_name="model-usd",
            usage=_usage(100, 0),
            reporting_currency="CNY",
            accounting_date=TODAY,
        ),
        service.stage_cost(
            stage="llm_compose",
            status="called",
            profile_name="chat",
            model_name="model-cny",
            usage=_usage(200, 0),
            reporting_currency="CNY",
            accounting_date=TODAY,
        ),
    ]

    cost = service.run_cost(stages=stages, reporting_currency="CNY")

    assert cost.status == "complete"
    assert [(item.currency, item.amount) for item in cost.billing_totals] == [
        ("CNY", Decimal("0.000200000000")),
        ("USD", Decimal("0.000100000000")),
    ]
    assert cost.reporting_total.amount == Decimal("0.000920000000")


def test_missing_exchange_rate_preserves_native_amount_without_reporting_zero():
    service = CostingService(
        profiles={
            "chat": _profile(
                "chat",
                model="model-usd",
                currency="USD",
                input_rate="1",
                output_rate="1",
            )
        }
    )
    stage = service.stage_cost(
        stage="llm_compose",
        status="called",
        profile_name="chat",
        model_name="model-usd",
        usage=_usage(100, 0),
        reporting_currency="CNY",
        accounting_date=TODAY,
    )
    cost = service.run_cost(stages=[stage], reporting_currency="CNY")

    assert cost.status == "partial"
    assert cost.issues == ["missing_exchange_rate"]
    assert cost.billing_totals[0].amount == Decimal("0.000100000000")
    assert cost.reporting_total is None


def test_zero_usage_is_not_applicable_not_missing_pricing():
    service = CostingService(profiles={})
    stage = service.stage_cost(
        stage="route_classify",
        status="failed",
        profile_name="missing",
        model_name=None,
        usage=None,
        reporting_currency="USD",
        accounting_date=TODAY,
    )
    cost = service.run_cost(stages=[stage], reporting_currency="USD")

    assert cost.status == "not_applicable"
    assert cost.issues == []


def test_reporting_currency_is_normalized_and_validated():
    assert CostSettings(reporting_currency="cny").reporting_currency == "CNY"


def test_stage_entry_costing_reuses_exchange_rate_per_currency_pair():
    lookup_calls = []

    def lookup(billing: str, reporting: str, on_date: date):
        lookup_calls.append((billing, reporting, on_date))
        return ExchangeRateSnapshot(
            billing_currency=billing,
            reporting_currency=reporting,
            exchange_rate=Decimal("7.2"),
            exchange_rate_date=on_date,
            exchange_rate_source="test-fx",
        )

    service = CostingService(
        profiles={
            "router": _profile(
                "router",
                model="model-usd",
                currency="USD",
                input_rate="1",
                output_rate="1",
            )
        },
        exchange_rate_lookup=lookup,
    )
    stage_entries = {
        "turn_contextualize": {
            "status": "called",
            "profile": "router",
            "model_name": "model-usd",
            "input_tokens": 10,
        },
        "route_classify": {
            "status": "called",
            "profile": "router",
            "model_name": "model-usd",
            "input_tokens": 20,
        },
    }

    cost = service.cost_stage_entries(
        stage_entries,
        reporting_currency="CNY",
        accounting_date=TODAY,
    )

    assert cost.status == "complete"
    assert lookup_calls == [("USD", "CNY", TODAY)]
