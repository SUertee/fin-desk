"""Business operations for explicit finance content subscriptions."""

from __future__ import annotations

from collections.abc import Callable

from app.connectors.rss.errors import RSSConnectorError
from app.connectors.rss.opml import parse_opml
from app.connectors.rss.security import validate_external_feed_url
from app.models.subscriptions import (
    ContentSubscription,
    ContentSubscriptionCreate,
    ContentSubscriptionUpdate,
    OPMLImportResult,
    SubscriptionCreateResult,
)
from app.services.inbox_errors import FinanceInboxError


class SubscriptionService:
    def __init__(
        self,
        *,
        create_or_get: Callable[..., tuple[ContentSubscription, bool]],
        list_subscriptions: Callable[..., list[ContentSubscription]],
        update_subscription: Callable[..., ContentSubscription | None],
        url_validator: Callable[[str], str] = validate_external_feed_url,
        max_opml_bytes: int = 1_000_000,
        max_opml_outlines: int = 200,
    ) -> None:
        self.create_or_get = create_or_get
        self.list_reader = list_subscriptions
        self.update_writer = update_subscription
        self.url_validator = url_validator
        self.max_opml_bytes = max_opml_bytes
        self.max_opml_outlines = max_opml_outlines

    def create(
        self,
        user_id: str,
        payload: ContentSubscriptionCreate | dict,
    ) -> SubscriptionCreateResult:
        parsed = ContentSubscriptionCreate.model_validate(payload)
        try:
            normalized = self.url_validator(parsed.feed_url)
        except RSSConnectorError as exc:
            raise FinanceInboxError(exc.code) from exc
        subscription, created = self.create_or_get(
            user_id,
            name=parsed.name,
            feed_url=parsed.feed_url.strip(),
            normalized_feed_url=normalized,
        )
        return SubscriptionCreateResult(subscription=subscription, created=created)

    def list(self, user_id: str) -> list[ContentSubscription]:
        return self.list_reader(user_id, enabled_only=False, limit=200)

    def update(
        self,
        user_id: str,
        subscription_id: str,
        payload: ContentSubscriptionUpdate | dict,
    ) -> ContentSubscription:
        parsed = ContentSubscriptionUpdate.model_validate(payload)
        if parsed.name is None and parsed.enabled is None:
            raise FinanceInboxError("empty_update")
        updated = self.update_writer(
            user_id,
            subscription_id,
            name=parsed.name,
            enabled=parsed.enabled,
        )
        if updated is None:
            raise FinanceInboxError("not_found")
        return updated

    def import_opml(self, user_id: str, payload: bytes) -> OPMLImportResult:
        try:
            feeds = parse_opml(
                payload,
                max_bytes=self.max_opml_bytes,
                max_outlines=self.max_opml_outlines,
            )
        except RSSConnectorError as exc:
            raise FinanceInboxError(exc.code) from exc
        result = OPMLImportResult()
        for feed in feeds:
            try:
                created = self.create(
                    user_id,
                    ContentSubscriptionCreate(name=feed.name, feed_url=feed.feed_url),
                )
                result.subscriptions.append(created.subscription)
                if created.created:
                    result.created_count += 1
                else:
                    result.existing_count += 1
            except FinanceInboxError as exc:
                if exc.code in {"unsafe_url", "unsafe_port", "dns_resolution_failed"}:
                    result.rejected_count += 1
                else:
                    result.invalid_count += 1
                if len(result.errors) < 20:
                    result.errors.append(exc.code)
        return result
