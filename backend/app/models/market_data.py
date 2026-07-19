"""Provider-neutral contracts for read-only external market data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.costing import MoneyAmount, normalize_currency
from app.models.investments import MarketInstrument, MarketQuote, normalize_symbol


MarketAssetType = Literal["equity", "etf"]
MarketOperation = Literal["quote", "history", "profile"]
MarketInterval = Literal["1d"]
MarketProviderAvailability = Literal["available", "unavailable"]


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class MarketCacheMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_hit: bool
    cache_key: str = Field(min_length=16, max_length=128)
    provider: str = Field(min_length=1, max_length=80)
    fetched_at: datetime
    expires_at: datetime

    @field_validator("fetched_at", "expires_at")
    @classmethod
    def validate_datetime(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @model_validator(mode="after")
    def validate_expiry(self) -> "MarketCacheMetadata":
        if self.expires_at <= self.fetched_at:
            raise ValueError("cache expiry must be after fetch time")
        return self


class ExternalCallUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget: int = Field(ge=0)
    used: int = Field(ge=0)
    remaining: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_accounting(self) -> "ExternalCallUsage":
        if self.used + self.remaining != self.budget:
            raise ValueError("external call usage must balance")
        return self


class MarketQuoteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=80)
    fetched_at: datetime
    quotes: list[MarketQuote] = Field(default_factory=list)
    missing: list[MarketInstrument] = Field(default_factory=list)
    cache: MarketCacheMetadata
    external_calls: ExternalCallUsage

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, value: datetime) -> datetime:
        return _aware_datetime(value)


class MarketPriceBar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    asset_type: MarketAssetType
    interval: MarketInterval = "1d"
    period: date
    open: MoneyAmount
    high: MoneyAmount
    low: MoneyAmount
    close: MoneyAmount
    volume: int | None = Field(default=None, ge=0)
    source: str = Field(min_length=1, max_length=120)
    venue: str = Field(default="", max_length=80)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @model_validator(mode="after")
    def validate_prices(self) -> "MarketPriceBar":
        currencies = {self.open.currency, self.high.currency, self.low.currency, self.close.currency}
        if len(currencies) != 1:
            raise ValueError("OHLC currencies must match")
        if any(value.amount <= 0 for value in (self.open, self.high, self.low, self.close)):
            raise ValueError("OHLC prices must be positive")
        if self.low.amount > self.high.amount:
            raise ValueError("low price cannot exceed high price")
        return self


class MarketPriceHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    asset_type: MarketAssetType
    provider: str = Field(min_length=1, max_length=80)
    interval: MarketInterval = "1d"
    currency: str
    date_from: date
    date_to: date
    fetched_at: datetime
    bars: list[MarketPriceBar] = Field(default_factory=list)
    cache: MarketCacheMetadata
    external_calls: ExternalCallUsage

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @model_validator(mode="after")
    def validate_range(self) -> "MarketPriceHistory":
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class MarketInstrumentData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    asset_type: MarketAssetType
    name: str = Field(min_length=1, max_length=240)
    venue: str = Field(default="", max_length=80)
    currency: str
    sector: str | None = Field(default=None, max_length=160)
    industry: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=120)
    source: str = Field(min_length=1, max_length=120)
    fetched_at: datetime

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, value: datetime) -> datetime:
        return _aware_datetime(value)


class MarketInstrumentProfile(MarketInstrumentData):
    cache: MarketCacheMetadata
    external_calls: ExternalCallUsage


class MarketProviderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: str = "openbb"
    availability: MarketProviderAvailability
    configured_provider: str
    allowed: bool
    supported_operations: list[MarketOperation]
    supported_asset_types: list[MarketAssetType]
    detail: str | None = Field(default=None, max_length=240)


class MarketCacheEntry(BaseModel):
    """Internal normalized cache record persisted as JSON, never an SDK object."""

    model_config = ConfigDict(extra="forbid")

    cache_key: str = Field(min_length=16, max_length=128)
    operation: MarketOperation
    provider: str = Field(min_length=1, max_length=80)
    payload: dict
    fetched_at: datetime
    expires_at: datetime

    @field_validator("fetched_at", "expires_at")
    @classmethod
    def validate_datetime(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @model_validator(mode="after")
    def validate_expiry(self) -> "MarketCacheEntry":
        if self.expires_at <= self.fetched_at:
            raise ValueError("cache expiry must be after fetch time")
        return self
