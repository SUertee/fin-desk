"""Typed contracts for read-only investment portfolio analysis."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.costing import ExchangeRateSnapshot, MoneyAmount, normalize_currency


InvestmentAccountType = Literal["brokerage", "retirement", "crypto", "other"]
InvestmentAccountStatus = Literal["active", "disconnected"]
InvestmentAssetType = Literal["equity", "etf", "fund", "bond", "crypto", "cash", "other"]
PortfolioStatus = Literal["empty", "partial", "complete"]
InvestmentRiskSeverity = Literal["info", "medium", "high"]
InvestmentRiskCode = Literal[
    "disconnected_account",
    "missing_quote",
    "stale_quote",
    "missing_exchange_rate",
    "single_position_concentration",
]
MarketQuoteTimestampBasis = Literal["provider_time", "retrieval_time"]
PositionValuationIssue = Literal[
    "missing_quote",
    "stale_quote",
    "missing_exchange_rate",
]


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


def normalize_symbol(value: str) -> str:
    normalized = str(value).strip().upper()
    if not normalized or len(normalized) > 64:
        raise ValueError("symbol must contain between 1 and 64 characters")
    return normalized


class MarketInstrument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    asset_type: InvestmentAssetType

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)


class InvestmentAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    account_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=160)
    account_type: InvestmentAccountType = "brokerage"
    provider: str = Field(default="manual", min_length=1, max_length=80)
    base_currency: str = "CNY"
    status: InvestmentAccountStatus = "active"
    as_of: datetime

    @field_validator("base_currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware_datetime(value)


class InvestmentPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    account_id: str = Field(min_length=1, max_length=128)
    symbol: str
    asset_type: InvestmentAssetType
    quantity: Decimal = Field(gt=0)
    average_cost: MoneyAmount | None = None
    as_of: datetime

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @property
    def instrument(self) -> MarketInstrument:
        return MarketInstrument(symbol=self.symbol, asset_type=self.asset_type)


class MarketQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    asset_type: InvestmentAssetType
    price: MoneyAmount
    quote_as_of: datetime
    timestamp_basis: MarketQuoteTimestampBasis = "provider_time"
    source: str = Field(min_length=1, max_length=120)
    venue: str = Field(default="", max_length=80)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("price")
    @classmethod
    def validate_positive_price(cls, value: MoneyAmount) -> MoneyAmount:
        if value.amount <= 0:
            raise ValueError("market quote price must be positive")
        return value

    @field_validator("quote_as_of")
    @classmethod
    def validate_quote_as_of(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @property
    def instrument(self) -> MarketInstrument:
        return MarketInstrument(symbol=self.symbol, asset_type=self.asset_type)


class MarketQuoteBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=120)
    as_of: datetime
    quotes: list[MarketQuote] = Field(default_factory=list)
    missing: list[MarketInstrument] = Field(default_factory=list)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware_datetime(value)


class PositionValuation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    symbol: str
    asset_type: InvestmentAssetType
    quantity: Decimal
    quote: MarketQuote | None = None
    native_market_value: MoneyAmount | None = None
    reporting_market_value: MoneyAmount | None = None
    exchange_rate_snapshot: ExchangeRateSnapshot | None = None
    issues: list[PositionValuationIssue] = Field(default_factory=list)


class InvestmentRiskFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: InvestmentRiskCode
    severity: InvestmentRiskSeverity
    title: str
    detail: str
    symbols: list[str] = Field(default_factory=list)
    account_ids: list[str] = Field(default_factory=list)
    measured_percent: Decimal | None = Field(default=None, ge=0)
    threshold_percent: Decimal | None = Field(default=None, ge=0)


class InvestmentRiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[InvestmentRiskFinding] = Field(default_factory=list)
    trade_actions_allowed: Literal[False] = False


class PortfolioCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_count: int = Field(default=0, ge=0)
    position_count: int = Field(default=0, ge=0)
    quoted_position_count: int = Field(default=0, ge=0)
    reporting_position_count: int = Field(default=0, ge=0)
    quote_sources: list[str] = Field(default_factory=list)
    latest_quote_as_of: datetime | None = None


class PortfolioSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    status: PortfolioStatus
    as_of: datetime
    reporting_currency: str
    accounts: list[InvestmentAccount] = Field(default_factory=list)
    positions: list[PositionValuation] = Field(default_factory=list)
    native_totals: list[MoneyAmount] = Field(default_factory=list)
    converted_subtotal: MoneyAmount | None = None
    reporting_total: MoneyAmount | None = None
    coverage: PortfolioCoverage = Field(default_factory=PortfolioCoverage)
    risk: InvestmentRiskAssessment = Field(default_factory=InvestmentRiskAssessment)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @field_validator("reporting_currency")
    @classmethod
    def validate_reporting_currency(cls, value: str) -> str:
        return normalize_currency(value)
