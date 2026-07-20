"""Provider-neutral contracts for governed external web research."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.market_data import ExternalCallUsage


WebResearchStatus = Literal["available", "partial", "unavailable"]
WebSearchProviderAvailability = Literal["available", "unavailable"]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


def normalize_domain(value: str) -> str:
    normalized = value.strip().lower().rstrip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    if not normalized or "/" in normalized or " " in normalized:
        raise ValueError("invalid source domain")
    return normalized


def source_domain(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source URL must be an absolute HTTP(S) URL")
    return normalize_domain(parsed.hostname)


class WebResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=500)
    domains: list[str] = Field(default_factory=list, max_length=20)
    max_results: int = Field(default=5, ge=1, le=10)
    topic: Literal["general", "news"] = "general"

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("domains")
    @classmethod
    def normalize_domains(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(normalize_domain(item) for item in value))


class WebSearchProviderItem(BaseModel):
    """Normalized provider output before FinDesk governance filtering."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=8, max_length=2048)
    snippet: str = Field(default="", max_length=4000)
    published_at: datetime | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        source_domain(value)
        return value.strip()

    @field_validator("published_at")
    @classmethod
    def validate_published_at(cls, value: datetime | None) -> datetime | None:
        return _aware(value) if value else None


class WebSearchProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=500)
    fetched_at: datetime
    items: list[WebSearchProviderItem] = Field(default_factory=list)

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, value: datetime) -> datetime:
        return _aware(value)


class WebResearchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str = Field(min_length=12, max_length=80)
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=8, max_length=2048)
    domain: str = Field(min_length=1, max_length=255)
    snippet: str = Field(default="", max_length=4000)
    provider: str = Field(min_length=1, max_length=80)
    published_at: datetime | None = None
    fetched_at: datetime
    score: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        source_domain(value)
        return value.strip()

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        return normalize_domain(value)

    @field_validator("published_at", "fetched_at")
    @classmethod
    def validate_times(cls, value: datetime | None) -> datetime | None:
        return _aware(value) if value else None


class WebResearchCacheMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_hit: bool
    cache_key: str = Field(min_length=16, max_length=128)
    fetched_at: datetime
    expires_at: datetime

    @field_validator("fetched_at", "expires_at")
    @classmethod
    def validate_times(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_expiry(self) -> "WebResearchCacheMetadata":
        if self.expires_at <= self.fetched_at:
            raise ValueError("cache expiry must be after fetch time")
        return self


class WebResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: WebResearchStatus
    provider: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=500)
    items: list[WebResearchItem] = Field(default_factory=list)
    excluded_count: int = Field(default=0, ge=0)
    limitations: list[str] = Field(default_factory=list)
    cache: WebResearchCacheMetadata | None = None
    external_calls: ExternalCallUsage


class WebSearchProviderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    availability: WebSearchProviderAvailability
    configured_provider: str
    allowed: bool
    detail: str | None = Field(default=None, max_length=240)


class WebResearchCacheEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_key: str = Field(min_length=16, max_length=128)
    provider: str = Field(min_length=1, max_length=80)
    payload: dict
    fetched_at: datetime
    expires_at: datetime

    @field_validator("fetched_at", "expires_at")
    @classmethod
    def validate_times(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_expiry(self) -> "WebResearchCacheEntry":
        if self.expires_at <= self.fetched_at:
            raise ValueError("cache expiry must be after fetch time")
        return self
