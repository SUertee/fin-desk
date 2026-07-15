"""Typed read models for the finance-facing AI Cost Explorer."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.costing import CostIssue, ExchangeRateSnapshot, MoneyAmount, normalize_currency


ExplorerStatus = Literal["complete", "partial", "empty"]
BudgetStatus = Literal[
    "not_configured",
    "on_track",
    "watch",
    "over_budget",
    "unavailable",
]


class AICostPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date
    date_to: date


class AICostCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_count: int = Field(default=0, ge=0)
    billable_run_count: int = Field(default=0, ge=0)
    complete_run_count: int = Field(default=0, ge=0)
    partial_run_count: int = Field(default=0, ge=0)
    provider_count: int = Field(default=0, ge=0)
    subscription_status: Literal["not_connected"] = "not_connected"
    latest_exchange_rate_date: date | None = None


class AICostBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: BudgetStatus = "not_configured"
    limit: MoneyAmount | None = None
    utilization_percent: Decimal | None = Field(default=None, ge=0)


class AICostSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracked_total: MoneyAmount | None = None
    api_usage_total: MoneyAmount | None = None
    converted_subtotal: MoneyAmount | None = None
    subscription_total: MoneyAmount | None = None
    budget: AICostBudget = Field(default_factory=AICostBudget)


class AICostTrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    status: Literal["complete", "partial"]
    reporting_total: MoneyAmount | None = None
    run_count: int = Field(default=0, ge=0)


class AICostBreakdownItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    reporting_total: MoneyAmount
    share_percent: Decimal = Field(ge=0, le=100)
    run_count: int = Field(default=0, ge=0)


class AICostItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    occurred_at: datetime
    entrypoint: str
    providers: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    status: Literal["complete", "partial"]
    issues: list[CostIssue] = Field(default_factory=list)
    billing_totals: list[MoneyAmount] = Field(default_factory=list)
    reporting_total: MoneyAmount | None = None
    exchange_rate_snapshots: list[ExchangeRateSnapshot] = Field(default_factory=list)


class AICostBreakdowns(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[AICostBreakdownItem] = Field(default_factory=list)
    models: list[AICostBreakdownItem] = Field(default_factory=list)
    entrypoints: list[AICostBreakdownItem] = Field(default_factory=list)


class AICostOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    period: AICostPeriod
    status: ExplorerStatus
    issues: list[CostIssue] = Field(default_factory=list)
    reporting_currency: str
    coverage: AICostCoverage = Field(default_factory=AICostCoverage)
    summary: AICostSummary = Field(default_factory=AICostSummary)
    trend: list[AICostTrendPoint] = Field(default_factory=list)
    breakdowns: AICostBreakdowns = Field(default_factory=AICostBreakdowns)
    items: list[AICostItem] = Field(default_factory=list)

    @field_validator("reporting_currency")
    @classmethod
    def validate_reporting_currency(cls, value: str) -> str:
        return normalize_currency(value)

