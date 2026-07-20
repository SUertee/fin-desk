"""Typed contracts for Finance Inbox content subscriptions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


RefreshStatus = Literal["never", "success", "partial", "failed"]
RefreshResultStatus = Literal["success", "partial", "unavailable", "failed"]


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("datetime must be timezone-aware")
    return value


class ContentSubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    feed_url: str = Field(min_length=8, max_length=2048)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())


class ContentSubscriptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value is not None else None


class ContentSubscription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=8, max_length=80)
    user_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    source_type: Literal["rss"] = "rss"
    feed_url: str = Field(min_length=8, max_length=2048)
    normalized_feed_url: str = Field(min_length=8, max_length=2048)
    enabled: bool = True
    last_refresh_status: RefreshStatus = "never"
    last_refresh_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_code: str | None = Field(default=None, max_length=80)
    etag: str | None = Field(default=None, max_length=500)
    last_modified: str | None = Field(default=None, max_length=500)
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "last_refresh_at", "last_success_at", "created_at", "updated_at"
    )
    @classmethod
    def validate_times(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class SubscriptionCreateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscription: ContentSubscription
    created: bool


class OPMLImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_count: int = Field(default=0, ge=0)
    existing_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    subscriptions: list[ContentSubscription] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list, max_length=20)


class RefreshResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RefreshResultStatus
    subscription_id: str | None = Field(default=None, max_length=80)
    fetched_count: int = Field(default=0, ge=0)
    created_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    source_link_count: int = Field(default=0, ge=0)
    fetched_at: datetime
    limitations: list[str] = Field(default_factory=list, max_length=20)
    error_code: str | None = Field(default=None, max_length=80)

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, value: datetime) -> datetime:
        return _aware(value)  # type: ignore[return-value]


class RefreshAllResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RefreshResultStatus
    results: list[RefreshResult] = Field(default_factory=list)
    fetched_count: int = Field(default=0, ge=0)
    created_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    source_link_count: int = Field(default=0, ge=0)
    fetched_at: datetime

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, value: datetime) -> datetime:
        return _aware(value)  # type: ignore[return-value]
