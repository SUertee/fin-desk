"""Deterministic RSS ingestion and cross-feed deduplication."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.connectors.rss.errors import RSSConnectorError
from app.connectors.rss.provider import RSSProvider
from app.models.finance_inbox import InboxItemWrite, InboxUpsertResult
from app.models.subscriptions import (
    ContentSubscription,
    RefreshAllResult,
    RefreshResult,
)
from app.services.inbox_errors import FinanceInboxError


_TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


def canonicalize_article_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in _TRACKING_PARAMETERS
    ]
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            urlencode(query, doseq=True),
            "",
        )
    )


def _digest(*parts: str) -> str:
    normalized = "\x1f".join(" ".join(part.lower().split()) for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_item_write(
    subscription: ContentSubscription,
    entry,
    fetched_at: datetime,
) -> InboxItemWrite:
    canonical_url = canonicalize_article_url(entry.url)
    if canonical_url:
        item_key = _digest("url", canonical_url)
    elif entry.feed_entry_id:
        item_key = _digest("guid", subscription.id, entry.feed_entry_id)
    else:
        published = entry.published_at.isoformat() if entry.published_at else ""
        item_key = _digest("fallback", subscription.id, entry.title, published)
    content_hash = _digest("content", entry.title, entry.excerpt)
    return InboxItemWrite(
        item_key=item_key,
        canonical_url=canonical_url,
        title=entry.title,
        excerpt=entry.excerpt,
        author=entry.author,
        published_at=entry.published_at,
        fetched_at=fetched_at,
        content_hash=content_hash,
        feed_entry_id=entry.feed_entry_id,
    )


class InboxIngestionService:
    def __init__(
        self,
        *,
        provider: RSSProvider,
        get_subscription,
        list_subscriptions,
        upsert_items,
        update_refresh,
    ) -> None:
        self.provider = provider
        self.get_subscription = get_subscription
        self.list_subscriptions = list_subscriptions
        self.upsert_items = upsert_items
        self.update_refresh = update_refresh

    def refresh_one(self, user_id: str, subscription_id: str) -> RefreshResult:
        attempted_at = datetime.now(timezone.utc)
        subscription = self.get_subscription(user_id, subscription_id)
        if subscription is None:
            raise FinanceInboxError("not_found")
        if not subscription.enabled:
            raise FinanceInboxError("subscription_disabled")
        try:
            document = self.provider.fetch(subscription)
            writes = [
                build_item_write(subscription, entry, document.fetched_at)
                for entry in document.entries
            ]
            upserted = (
                self.upsert_items(user_id, subscription.id, subscription.name, writes)
                if writes
                else InboxUpsertResult()
            )
            status = "partial" if document.invalid_count else "success"
            self.update_refresh(
                user_id,
                subscription.id,
                status=status,
                attempted_at=document.fetched_at,
                error_code=None,
                etag=document.etag,
                last_modified=document.last_modified,
            )
            return RefreshResult(
                status=status,
                subscription_id=subscription.id,
                fetched_count=len(document.entries),
                created_count=upserted.created_count,
                duplicate_count=upserted.duplicate_count,
                invalid_count=document.invalid_count,
                source_link_count=upserted.source_link_count,
                fetched_at=document.fetched_at,
                limitations=(
                    [f"{document.invalid_count} invalid feed entries were skipped"]
                    if document.invalid_count
                    else []
                ),
            )
        except RSSConnectorError as exc:
            self.update_refresh(
                user_id,
                subscription.id,
                status="failed",
                attempted_at=attempted_at,
                error_code=exc.code,
            )
            return RefreshResult(
                status=(
                    "unavailable"
                    if exc.code in {"provider_unavailable", "fetch_timeout"}
                    else "failed"
                ),
                subscription_id=subscription.id,
                fetched_at=attempted_at,
                error_code=exc.code,
                limitations=["Source refresh failed; existing Inbox content is unchanged"],
            )

    def refresh_all(self, user_id: str) -> RefreshAllResult:
        attempted_at = datetime.now(timezone.utc)
        subscriptions = self.list_subscriptions(
            user_id,
            enabled_only=True,
            limit=200,
        )
        results = [self.refresh_one(user_id, item.id) for item in subscriptions]
        successful = sum(item.status in {"success", "partial"} for item in results)
        if not results or successful == len(results):
            status = "success"
        elif successful:
            status = "partial"
        else:
            status = "failed"
        return RefreshAllResult(
            status=status,
            results=results,
            fetched_count=sum(item.fetched_count for item in results),
            created_count=sum(item.created_count for item in results),
            duplicate_count=sum(item.duplicate_count for item in results),
            invalid_count=sum(item.invalid_count for item in results),
            source_link_count=sum(item.source_link_count for item in results),
            fetched_at=max((item.fetched_at for item in results), default=attempted_at),
        )
