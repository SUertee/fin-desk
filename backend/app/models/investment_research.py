"""Typed contracts for watchlists and hypothetical investment research."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.costing import ExchangeRateSnapshot, MoneyAmount, normalize_currency
from app.models.investments import (
    InvestmentRiskAssessment,
    MarketQuote,
    normalize_symbol,
)
from app.models.market_data import (
    MarketAssetType,
    MarketInstrumentProfile,
    MarketPriceHistory,
)


ScenarioValuationStatus = Literal["empty", "partial", "complete"]
PerformanceStatus = Literal["available", "insufficient_data"]
BenchmarkComparisonStatus = Literal["available", "unavailable", "insufficient_data"]
InvestmentReadinessStatus = Literal["ready", "caution", "insufficient_data"]
InvestmentReadinessSeverity = Literal["info", "medium", "high"]
InvestmentReadinessCode = Literal[
    "missing_monthly_income",
    "missing_monthly_expenses",
    "negative_monthly_cash_flow",
    "low_liquid_reserve",
    "liabilities_present",
]
ResearchEvidenceKind = Literal[
    "profile",
    "quote",
    "history",
    "benchmark_history",
    "exchange_rate",
]
ScenarioValuationIssue = Literal["missing_quote", "missing_exchange_rate"]


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class WatchlistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    symbol: str
    asset_type: MarketAssetType = "equity"
    note: str = Field(default="", max_length=500)
    created_at: datetime
    updated_at: datetime

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_datetime(cls, value: datetime) -> datetime:
        return _aware_datetime(value)


class WatchlistItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    asset_type: MarketAssetType = "equity"
    note: str = Field(default="", max_length=500)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)


class InvestmentScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    scenario_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=160)
    reporting_currency: str = "CNY"
    starting_cash: MoneyAmount | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("reporting_currency")
    @classmethod
    def validate_reporting_currency(cls, value: str) -> str:
        return normalize_currency(value)

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_datetime(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @model_validator(mode="after")
    def validate_starting_cash_currency(self) -> "InvestmentScenario":
        if self.starting_cash and self.starting_cash.currency != self.reporting_currency:
            raise ValueError("starting cash must use the scenario reporting currency")
        return self


class InvestmentScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    reporting_currency: str = "CNY"
    starting_cash_amount: Decimal | None = Field(default=None, ge=0)

    @field_validator("reporting_currency")
    @classmethod
    def validate_reporting_currency(cls, value: str) -> str:
        return normalize_currency(value)


class ScenarioPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    scenario_id: str = Field(min_length=1, max_length=128)
    symbol: str
    asset_type: MarketAssetType = "equity"
    quantity: Decimal = Field(gt=0)
    created_at: datetime
    updated_at: datetime

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_datetime(cls, value: datetime) -> datetime:
        return _aware_datetime(value)


class ScenarioPositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    asset_type: MarketAssetType = "equity"
    quantity: Decimal = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)


class ScenarioPositionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    positions: list[ScenarioPositionRequest] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_unique_instruments(self) -> "ScenarioPositionsRequest":
        instruments = [(item.symbol, item.asset_type) for item in self.positions]
        if len(instruments) != len(set(instruments)):
            raise ValueError("scenario positions must be unique by symbol and asset type")
        return self


class InvestmentScenarioDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: InvestmentScenario
    positions: list[ScenarioPosition] = Field(default_factory=list)


class ResearchEvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ResearchEvidenceKind
    source: str = Field(min_length=1, max_length=160)
    as_of: datetime | date
    description: str = Field(min_length=1, max_length=240)


class HistoricalPerformanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PerformanceStatus
    symbol: str
    currency: str
    observation_count: int = Field(default=0, ge=0)
    date_from: date | None = None
    date_to: date | None = None
    period_return_percent: Decimal | None = None
    annualized_volatility_percent: Decimal | None = Field(default=None, ge=0)
    max_drawdown_percent: Decimal | None = Field(default=None, ge=0, le=100)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)


class BenchmarkComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: BenchmarkComparisonStatus
    benchmark_symbol: str
    performance: HistoricalPerformanceSummary | None = None
    excess_period_return_percent: Decimal | None = None
    limitation: str | None = Field(default=None, max_length=300)

    @field_validator("benchmark_symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)


class InvestmentReadinessFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: InvestmentReadinessCode
    severity: InvestmentReadinessSeverity
    title: str = Field(min_length=1, max_length=160)
    detail: str = Field(min_length=1, max_length=360)


class InvestmentReadinessAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: InvestmentReadinessStatus
    reporting_currency: str
    monthly_cash_flow: Decimal | None = None
    liquid_reserve: MoneyAmount | None = None
    reserve_months: Decimal | None = Field(default=None, ge=0)
    liabilities: MoneyAmount | None = None
    risk_tolerance: str = Field(default="moderate", min_length=1, max_length=80)
    findings: list[InvestmentReadinessFinding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trade_actions_allowed: Literal[False] = False

    @field_validator("reporting_currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)


class InstrumentResearchSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    symbol: str
    asset_type: MarketAssetType
    followed: bool
    profile: MarketInstrumentProfile
    quote: MarketQuote | None = None
    history: MarketPriceHistory
    performance: HistoricalPerformanceSummary
    benchmark: BenchmarkComparison
    readiness: InvestmentReadinessAssessment
    evidence: list[ResearchEvidenceSource] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trade_actions_allowed: Literal[False] = False

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)


class ScenarioPositionValuation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    asset_type: MarketAssetType
    quantity: Decimal
    quote: MarketQuote | None = None
    native_market_value: MoneyAmount | None = None
    reporting_market_value: MoneyAmount | None = None
    exchange_rate_snapshot: ExchangeRateSnapshot | None = None
    issues: list[ScenarioValuationIssue] = Field(default_factory=list)


class ScenarioCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_count: int = Field(default=0, ge=0)
    quoted_position_count: int = Field(default=0, ge=0)
    reporting_position_count: int = Field(default=0, ge=0)
    quote_sources: list[str] = Field(default_factory=list)


class InvestmentScenarioValuation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ScenarioValuationStatus
    scenario: InvestmentScenario
    as_of: datetime
    positions: list[ScenarioPositionValuation] = Field(default_factory=list)
    native_totals: list[MoneyAmount] = Field(default_factory=list)
    converted_subtotal: MoneyAmount | None = None
    reporting_total: MoneyAmount | None = None
    remaining_cash: MoneyAmount | None = None
    overallocated_amount: MoneyAmount | None = None
    coverage: ScenarioCoverage = Field(default_factory=ScenarioCoverage)
    risk: InvestmentRiskAssessment = Field(default_factory=InvestmentRiskAssessment)
    readiness: InvestmentReadinessAssessment
    limitations: list[str] = Field(default_factory=list)
    trade_actions_allowed: Literal[False] = False

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware_datetime(value)
