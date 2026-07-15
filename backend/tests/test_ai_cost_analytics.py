from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.cost_explorer import AICostOverview
from app.models.costing import ExchangeRateSnapshot
from app.models.runtime import AgentRunRecord
from app.models.user import CostReportingPreferences, UserProfile
from app.routes import ai_costs
from app.services.ai_cost_analytics import AICostAnalyticsService


def _record(
    request_id: str,
    *,
    user_id: str = "demo",
    amount: str = "1",
    currency: str = "USD",
    issue: str | None = None,
) -> AgentRunRecord:
    cost = {
        "status": "partial" if issue else "complete",
        "issues": [issue] if issue else [],
        "reporting_currency": currency,
        "billing_totals": [] if issue == "missing_pricing" else [
            {"amount": amount, "currency": currency}
        ],
        "reporting_total": None,
        "stages": [
            {
                "stage": "llm_compose",
                "status": "called",
                "profile": "chat",
                "provider": "openai",
                "model_name": "gpt-4o",
                "billing_total": {"amount": amount, "currency": currency},
            }
        ] if not issue else [],
    }
    return AgentRunRecord(
        request_id=request_id,
        entrypoint="chat",
        user_id=user_id,
        runtime_requested="self_hosted",
        cost=cost,
        latency_ms=10,
    )


def _row(record: AgentRunRecord, day: int = 5):
    return {
        "record": record.model_dump(mode="json"),
        "created_at": datetime(2026, 7, day, 12, tzinfo=timezone.utc),
    }


def test_complete_overview_aggregates_run_cost_and_budget():
    captured = {}

    def read_records(**kwargs):
        captured.update(kwargs)
        return [_row(_record("run-1"))]

    service = AICostAnalyticsService(
        records_reader=read_records,
        exchange_rate_lookup=lambda *_: None,
    )
    overview = service.overview(
        user_id="demo",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        reporting_currency="USD",
        monthly_budget={"amount": "10", "currency": "USD"},
    )

    assert captured["user_id"] == "demo"
    assert overview.status == "complete"
    assert overview.summary.tracked_total.amount == Decimal("1.000000000000")
    assert overview.summary.budget.status == "on_track"
    assert overview.summary.budget.utilization_percent == Decimal("10.0")
    assert overview.coverage.provider_count == 1
    assert overview.breakdowns.providers[0].label == "openai"
    assert overview.breakdowns.providers[0].share_percent == Decimal("100.0")
    assert overview.items[0].request_id == "run-1"


def test_cross_currency_overview_uses_historical_snapshot():
    def lookup(billing: str, reporting: str, on_date: date):
        assert (billing, reporting, on_date) == ("USD", "CNY", date(2026, 7, 5))
        return ExchangeRateSnapshot(
            billing_currency=billing,
            reporting_currency=reporting,
            exchange_rate="7.2",
            exchange_rate_date="2026-07-04",
            exchange_rate_source="test-fx",
        )

    service = AICostAnalyticsService(
        records_reader=lambda **_: [_row(_record("run-1"))],
        exchange_rate_lookup=lookup,
    )
    overview = service.overview(
        user_id="demo",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        reporting_currency="CNY",
    )

    assert overview.status == "complete"
    assert overview.summary.tracked_total.amount == Decimal("7.200000000000")
    assert overview.coverage.latest_exchange_rate_date == date(2026, 7, 4)
    assert overview.items[0].billing_totals[0].currency == "USD"


def test_missing_exchange_rate_is_partial_without_fabricated_total():
    service = AICostAnalyticsService(
        records_reader=lambda **_: [_row(_record("run-1"))],
        exchange_rate_lookup=lambda *_: None,
    )
    overview = service.overview(
        user_id="demo",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        reporting_currency="CNY",
        monthly_budget={"amount": "300", "currency": "CNY"},
    )

    assert overview.status == "partial"
    assert overview.issues == ["missing_exchange_rate"]
    assert overview.summary.tracked_total is None
    assert overview.summary.api_usage_total is None
    assert overview.summary.budget.status == "unavailable"
    assert overview.items[0].billing_totals[0].amount == Decimal("1")


def test_empty_overview_and_user_isolation_are_explicit():
    service = AICostAnalyticsService(
        records_reader=lambda **_: [
            _row(_record("other", user_id="another-user")),
            _row(_record("outside"), day=1),
        ],
        exchange_rate_lookup=lambda *_: None,
    )
    overview = service.overview(
        user_id="demo",
        date_from=date(2026, 7, 2),
        date_to=date(2026, 7, 31),
        reporting_currency="USD",
    )

    assert overview.status == "empty"
    assert overview.coverage.run_count == 0
    assert overview.summary.tracked_total is None
    assert overview.items == []


def test_route_uses_profile_currency_and_rejects_excessive_period(monkeypatch):
    calls = {}

    class FakeService:
        def overview(self, **kwargs):
            calls.update(kwargs)
            return AICostOverview(
                user_id=kwargs["user_id"],
                period={
                    "date_from": kwargs["date_from"],
                    "date_to": kwargs["date_to"],
                },
                status="empty",
                reporting_currency=kwargs["reporting_currency"],
            )

    monkeypatch.setattr(ai_costs, "_service", FakeService())
    monkeypatch.setattr(
        ai_costs,
        "get_profile",
        lambda user_id: UserProfile(
            user_id=user_id,
            cost_preferences=CostReportingPreferences(
                reporting_currency="CNY", monthly_ai_budget="300"
            ),
        ),
    )

    result = ai_costs.get_ai_cost_overview(
        "demo", date(2026, 7, 1), date(2026, 7, 31), None
    )
    assert result.reporting_currency == "CNY"
    assert calls["monthly_budget"].amount == Decimal("300")

    with pytest.raises(HTTPException) as exc:
        ai_costs.get_ai_cost_overview(
            "demo", date(2025, 1, 1), date(2026, 7, 31), "USD"
        )
    assert exc.value.status_code == 400

