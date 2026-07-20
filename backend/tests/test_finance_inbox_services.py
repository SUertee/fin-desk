from datetime import datetime, timedelta, timezone

import pytest

from app.connectors.rss.errors import RSSConnectorError
from app.models.finance_inbox import (
    FeedDocument,
    InboxItem,
    InboxUpsertResult,
    NormalizedFeedEntry,
)
from app.models.subscriptions import ContentSubscription
from app.services.inbox_ingestion import (
    InboxIngestionService,
    build_item_write,
    canonicalize_article_url,
)
from app.services.inbox_errors import FinanceInboxError
from app.services.inbox_query import InboxQueryService
from app.services.subscriptions import SubscriptionService


NOW = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


def make_subscription(
    *,
    subscription_id: str = "subscription-1",
    enabled: bool = True,
) -> ContentSubscription:
    return ContentSubscription(
        id=subscription_id,
        user_id="demo",
        name="Finance Daily",
        feed_url="https://example.com/feed.xml",
        normalized_feed_url="https://example.com/feed.xml",
        enabled=enabled,
        created_at=NOW,
        updated_at=NOW,
    )


def test_subscription_create_and_opml_import_are_idempotent():
    rows = {}

    def create_or_get(user_id, *, name, feed_url, normalized_feed_url):
        key = (user_id, normalized_feed_url)
        created = key not in rows
        if created:
            rows[key] = make_subscription(subscription_id=f"subscription-{len(rows)+1}")
        return rows[key], created

    service = SubscriptionService(
        create_or_get=create_or_get,
        list_subscriptions=lambda *args, **kwargs: list(rows.values()),
        update_subscription=lambda *args, **kwargs: None,
        url_validator=lambda value: value.lower().replace("#latest", ""),
    )
    payload = b'''<opml><body>
      <outline text="One" xmlUrl="https://EXAMPLE.com/feed.xml#latest" />
    </body></opml>'''

    first = service.import_opml("demo", payload)
    second = service.import_opml("demo", payload)

    assert first.created_count == 1
    assert second.existing_count == 1
    assert len(rows) == 1


def test_canonicalize_article_url_drops_tracking_parameters():
    assert canonicalize_article_url(
        "https://Example.com/news?id=1&utm_source=rss&fbclid=abc#top"
    ) == "https://example.com/news?id=1"


def test_item_identity_prefers_canonical_url_and_has_content_hash():
    subscription = make_subscription()
    entry = NormalizedFeedEntry(
        title="Market update",
        url="https://example.com/news?utm_medium=rss",
        excerpt="Rates were unchanged.",
        feed_entry_id="guid-1",
    )

    write = build_item_write(subscription, entry, NOW)

    assert write.canonical_url == "https://example.com/news"
    assert len(write.item_key) == 64
    assert len(write.content_hash) == 64


def test_refresh_one_returns_counts_and_updates_refresh_state():
    subscription = make_subscription()
    states = []

    class Provider:
        def fetch(self, selected):
            return FeedDocument(
                feed_url=selected.feed_url,
                final_url=selected.feed_url,
                fetched_at=NOW,
                entries=[
                    NormalizedFeedEntry(
                        title="Market update",
                        url="https://example.com/news",
                        excerpt="Rates unchanged",
                    )
                ],
            )

    service = InboxIngestionService(
        provider=Provider(),
        get_subscription=lambda user_id, subscription_id: subscription,
        list_subscriptions=lambda *args, **kwargs: [subscription],
        upsert_items=lambda *args: InboxUpsertResult(
            created_count=1,
            source_link_count=1,
        ),
        update_refresh=lambda *args, **kwargs: states.append(kwargs),
    )

    result = service.refresh_one("demo", subscription.id)

    assert result.status == "success"
    assert result.fetched_count == 1
    assert result.created_count == 1
    assert states[0]["status"] == "success"


def test_disabled_subscription_cannot_be_refreshed():
    selected = make_subscription(enabled=False)
    service = InboxIngestionService(
        provider=object(),
        get_subscription=lambda user_id, subscription_id: selected,
        list_subscriptions=lambda *args, **kwargs: [],
        upsert_items=lambda *args: InboxUpsertResult(),
        update_refresh=lambda *args, **kwargs: None,
    )

    with pytest.raises(FinanceInboxError) as raised:
        service.refresh_one("demo", selected.id)

    assert raised.value.code == "subscription_disabled"


def test_refresh_all_reports_partial_without_discarding_success():
    first = make_subscription(subscription_id="subscription-1")
    second = make_subscription(subscription_id="subscription-2")

    class Provider:
        def fetch(self, selected):
            if selected.id == second.id:
                raise RSSConnectorError("malformed_feed")
            return FeedDocument(
                feed_url=selected.feed_url,
                final_url=selected.feed_url,
                fetched_at=NOW,
                entries=[],
            )

    service = InboxIngestionService(
        provider=Provider(),
        get_subscription=lambda user_id, subscription_id: (
            first if subscription_id == first.id else second
        ),
        list_subscriptions=lambda *args, **kwargs: [first, second],
        upsert_items=lambda *args: InboxUpsertResult(),
        update_refresh=lambda *args, **kwargs: None,
    )

    result = service.refresh_all("demo")

    assert result.status == "partial"
    assert [item.status for item in result.results] == ["success", "failed"]
    assert result.results[1].error_code == "malformed_feed"


def make_item(index: int) -> InboxItem:
    created = NOW - timedelta(minutes=index)
    return InboxItem(
        id=f"inbox-item-{index}",
        user_id="demo",
        title=f"Item {index}",
        excerpt="",
        fetched_at=created,
        content_hash=f"content-hash-value-{index:02d}",
        created_at=created,
        updated_at=created,
    )


def test_inbox_query_cursor_round_trips_and_is_bounded():
    calls = []
    first_page = [make_item(1), make_item(2)]

    def list_items(*args, **kwargs):
        calls.append(kwargs)
        return (first_page, True) if len(calls) == 1 else ([make_item(3)], False)

    service = InboxQueryService(
        list_items=list_items,
        update_status=lambda *args: None,
        get_summary=lambda user_id: None,
    )

    first = service.list("demo", status="unread", limit=1000, cursor=None)
    second = service.list(
        "demo",
        status="unread",
        limit=30,
        cursor=first.next_cursor,
    )

    assert first.next_cursor
    assert calls[0]["limit"] == 50
    assert calls[1]["before_created_at"] == first_page[-1].created_at
    assert second.next_cursor is None
