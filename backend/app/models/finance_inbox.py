"""Typed contracts for normalized feed content and Finance Inbox reads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


InboxItemStatus = Literal["unread", "read", "saved", "dismissed"]


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("datetime must be timezone-aware")
    return value


class NormalizedFeedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    url: str | None = Field(default=None, max_length=2048)
    excerpt: str = Field(default="", max_length=2000)
    author: str | None = Field(default=None, max_length=200)
    published_at: datetime | None = None
    feed_entry_id: str | None = Field(default=None, max_length=500)

    @field_validator("published_at")
    @classmethod
    def validate_published_at(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class FeedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="rss", min_length=1, max_length=80)
    feed_url: str = Field(min_length=8, max_length=2048)
    final_url: str = Field(min_length=8, max_length=2048)
    feed_title: str = Field(default="", max_length=500)
    fetched_at: datetime
    entries: list[NormalizedFeedEntry] = Field(default_factory=list)
    invalid_count: int = Field(default=0, ge=0)
    etag: str | None = Field(default=None, max_length=500)
    last_modified: str | None = Field(default=None, max_length=500)
    not_modified: bool = False

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, value: datetime) -> datetime:
        return _aware(value)  # type: ignore[return-value]


class InboxItemSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscription_id: str = Field(min_length=8, max_length=80)
    source_name: str = Field(min_length=1, max_length=120)
    feed_entry_id: str | None = Field(default=None, max_length=500)
    discovered_at: datetime

    @field_validator("discovered_at")
    @classmethod
    def validate_discovered_at(cls, value: datetime) -> datetime:
        return _aware(value)  # type: ignore[return-value]


class InboxItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=8, max_length=80)
    user_id: str = Field(min_length=1, max_length=200)
    canonical_url: str | None = Field(default=None, max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    excerpt: str = Field(default="", max_length=2000)
    author: str | None = Field(default=None, max_length=200)
    published_at: datetime | None = None
    fetched_at: datetime
    content_hash: str = Field(min_length=16, max_length=128)
    status: InboxItemStatus = "unread"
    sources: list[InboxItemSource] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("published_at", "fetched_at", "created_at", "updated_at")
    @classmethod
    def validate_times(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class InboxPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[InboxItem] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, max_length=1000)


class InboxSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscription_count: int = Field(default=0, ge=0)
    enabled_subscription_count: int = Field(default=0, ge=0)
    unread_count: int = Field(default=0, ge=0)
    saved_count: int = Field(default=0, ge=0)
    last_refresh_at: datetime | None = None
    last_refresh_status: str | None = Field(default=None, max_length=80)

    @field_validator("last_refresh_at")
    @classmethod
    def validate_last_refresh_at(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class InboxItemStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: InboxItemStatus


class InboxItemWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_key: str = Field(min_length=16, max_length=128)
    canonical_url: str | None = Field(default=None, max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    excerpt: str = Field(default="", max_length=2000)
    author: str | None = Field(default=None, max_length=200)
    published_at: datetime | None = None
    fetched_at: datetime
    content_hash: str = Field(min_length=16, max_length=128)
    feed_entry_id: str | None = Field(default=None, max_length=500)

    @field_validator("published_at", "fetched_at")
    @classmethod
    def validate_write_times(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class InboxUpsertResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    source_link_count: int = Field(default=0, ge=0)
