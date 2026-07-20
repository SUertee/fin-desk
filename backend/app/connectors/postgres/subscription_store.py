"""PostgreSQL persistence for Finance Inbox subscriptions."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.connectors.postgres.connection import get_conn
from app.models.subscriptions import ContentSubscription


class SubscriptionStoreUnavailable(RuntimeError):
    pass


_SELECT = """
    SELECT id, user_id, name, source_type, feed_url, normalized_feed_url,
           enabled, last_refresh_status, last_refresh_at, last_success_at,
           last_error_code, etag, last_modified, created_at, updated_at
    FROM content_subscriptions
"""


def _subscription(row) -> ContentSubscription:
    return ContentSubscription(
        id=row[0],
        user_id=row[1],
        name=row[2],
        source_type=row[3],
        feed_url=row[4],
        normalized_feed_url=row[5],
        enabled=row[6],
        last_refresh_status=row[7],
        last_refresh_at=row[8],
        last_success_at=row[9],
        last_error_code=row[10],
        etag=row[11],
        last_modified=row[12],
        created_at=row[13],
        updated_at=row[14],
    )


def create_or_get_subscription_db(
    user_id: str,
    *,
    name: str,
    feed_url: str,
    normalized_feed_url: str,
) -> tuple[ContentSubscription, bool]:
    with get_conn() as conn:
        if not conn:
            raise SubscriptionStoreUnavailable("database_unavailable")
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO content_subscriptions (
                    id, user_id, name, feed_url, normalized_feed_url
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, normalized_feed_url) DO NOTHING
                RETURNING id
                """,
                (uuid4().hex, user_id, name, feed_url, normalized_feed_url),
            )
            inserted = cur.fetchone()
            cur.execute(
                _SELECT + " WHERE user_id = %s AND normalized_feed_url = %s",
                (user_id, normalized_feed_url),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise SubscriptionStoreUnavailable("subscription_write_failed")
    return _subscription(row), inserted is not None


def list_subscriptions_db(
    user_id: str,
    *,
    enabled_only: bool = False,
    limit: int = 200,
) -> list[ContentSubscription]:
    bounded = min(max(limit, 1), 200)
    with get_conn() as conn:
        if not conn:
            raise SubscriptionStoreUnavailable("database_unavailable")
        with conn.cursor() as cur:
            condition = " AND enabled = TRUE" if enabled_only else ""
            cur.execute(
                _SELECT
                + f" WHERE user_id = %s{condition} ORDER BY updated_at DESC LIMIT %s",
                (user_id, bounded),
            )
            return [_subscription(row) for row in cur.fetchall()]


def get_subscription_db(user_id: str, subscription_id: str) -> ContentSubscription | None:
    with get_conn() as conn:
        if not conn:
            raise SubscriptionStoreUnavailable("database_unavailable")
        with conn.cursor() as cur:
            cur.execute(
                _SELECT + " WHERE user_id = %s AND id = %s",
                (user_id, subscription_id),
            )
            row = cur.fetchone()
    return _subscription(row) if row else None


def update_subscription_db(
    user_id: str,
    subscription_id: str,
    *,
    name: str | None,
    enabled: bool | None,
) -> ContentSubscription | None:
    with get_conn() as conn:
        if not conn:
            raise SubscriptionStoreUnavailable("database_unavailable")
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE content_subscriptions
                SET name = COALESCE(%s, name),
                    enabled = COALESCE(%s, enabled),
                    updated_at = NOW()
                WHERE user_id = %s AND id = %s
                """,
                (name, enabled, user_id, subscription_id),
            )
            cur.execute(
                _SELECT + " WHERE user_id = %s AND id = %s",
                (user_id, subscription_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _subscription(row) if row else None


def update_subscription_refresh_db(
    user_id: str,
    subscription_id: str,
    *,
    status: str,
    attempted_at: datetime,
    error_code: str | None,
    etag: str | None = None,
    last_modified: str | None = None,
) -> None:
    with get_conn() as conn:
        if not conn:
            raise SubscriptionStoreUnavailable("database_unavailable")
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE content_subscriptions
                SET last_refresh_status = %s,
                    last_refresh_at = %s,
                    last_success_at = CASE
                        WHEN %s IN ('success', 'partial') THEN %s
                        ELSE last_success_at
                    END,
                    last_error_code = %s,
                    etag = COALESCE(%s, etag),
                    last_modified = COALESCE(%s, last_modified),
                    updated_at = NOW()
                WHERE user_id = %s AND id = %s
                """,
                (
                    status,
                    attempted_at,
                    status,
                    attempted_at,
                    error_code,
                    etag,
                    last_modified,
                    user_id,
                    subscription_id,
                ),
            )
        conn.commit()
