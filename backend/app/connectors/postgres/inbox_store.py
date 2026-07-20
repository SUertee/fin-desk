"""PostgreSQL persistence for normalized Finance Inbox items."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.connectors.postgres.connection import get_conn
from app.models.finance_inbox import (
    InboxItem,
    InboxItemSource,
    InboxItemWrite,
    InboxSummary,
    InboxUpsertResult,
)


class InboxStoreUnavailable(RuntimeError):
    pass


def upsert_inbox_items_db(
    user_id: str,
    subscription_id: str,
    source_name: str,
    entries: list[InboxItemWrite],
) -> InboxUpsertResult:
    created = 0
    duplicates = 0
    source_links = 0
    with get_conn() as conn:
        if not conn:
            raise InboxStoreUnavailable("database_unavailable")
        with conn.transaction():
            with conn.cursor() as cur:
                for entry in entries:
                    cur.execute(
                        """
                        SELECT id FROM inbox_items
                        WHERE user_id = %s
                          AND (
                              item_key = %s
                              OR (%s = TRUE AND content_hash = %s)
                          )
                        ORDER BY CASE WHEN item_key = %s THEN 0 ELSE 1 END
                        LIMIT 1
                        """,
                        (
                            user_id,
                            entry.item_key,
                            bool(entry.excerpt.strip()),
                            entry.content_hash,
                            entry.item_key,
                        ),
                    )
                    row = cur.fetchone()
                    if row:
                        item_id = row[0]
                        duplicates += 1
                    else:
                        item_id = uuid4().hex
                        cur.execute(
                            """
                            INSERT INTO inbox_items (
                                id, user_id, item_key, canonical_url, title,
                                excerpt, author, published_at, fetched_at,
                                content_hash
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (user_id, item_key) DO NOTHING
                            RETURNING id
                            """,
                            (
                                item_id,
                                user_id,
                                entry.item_key,
                                entry.canonical_url,
                                entry.title,
                                entry.excerpt,
                                entry.author,
                                entry.published_at,
                                entry.fetched_at,
                                entry.content_hash,
                            ),
                        )
                        inserted = cur.fetchone()
                        if inserted:
                            created += 1
                        else:
                            duplicates += 1
                            cur.execute(
                                "SELECT id FROM inbox_items WHERE user_id = %s AND item_key = %s",
                                (user_id, entry.item_key),
                            )
                            item_id = cur.fetchone()[0]
                    cur.execute(
                        """
                        INSERT INTO inbox_item_sources (
                            item_id, subscription_id, source_name,
                            feed_entry_id, discovered_at
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (item_id, subscription_id) DO NOTHING
                        RETURNING item_id
                        """,
                        (
                            item_id,
                            subscription_id,
                            source_name,
                            entry.feed_entry_id,
                            entry.fetched_at,
                        ),
                    )
                    if cur.fetchone():
                        source_links += 1
    return InboxUpsertResult(
        created_count=created,
        duplicate_count=duplicates,
        source_link_count=source_links,
    )


def list_inbox_items_db(
    user_id: str,
    *,
    status: str | None,
    limit: int,
    before_created_at: datetime | None = None,
    before_id: str | None = None,
) -> tuple[list[InboxItem], bool]:
    bounded = min(max(limit, 1), 50)
    conditions = ["user_id = %s"]
    params: list[object] = [user_id]
    if status:
        conditions.append("status = %s")
        params.append(status)
    if before_created_at and before_id:
        conditions.append("(created_at, id) < (%s, %s)")
        params.extend([before_created_at, before_id])
    params.append(bounded + 1)
    with get_conn() as conn:
        if not conn:
            raise InboxStoreUnavailable("database_unavailable")
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, canonical_url, title, excerpt, author,
                       published_at, fetched_at, content_hash, status,
                       created_at, updated_at
                FROM inbox_items
                WHERE """
                + " AND ".join(conditions)
                + " ORDER BY created_at DESC, id DESC LIMIT %s",
                params,
            )
            rows = cur.fetchall()
            visible = rows[:bounded]
            item_ids = [row[0] for row in visible]
            source_map: dict[str, list[InboxItemSource]] = {item_id: [] for item_id in item_ids}
            if item_ids:
                cur.execute(
                    """
                    SELECT item_id, subscription_id, source_name, feed_entry_id,
                           discovered_at
                    FROM inbox_item_sources
                    WHERE item_id = ANY(%s)
                    ORDER BY discovered_at ASC
                    """,
                    (item_ids,),
                )
                for source in cur.fetchall():
                    source_map[source[0]].append(
                        InboxItemSource(
                            subscription_id=source[1],
                            source_name=source[2],
                            feed_entry_id=source[3],
                            discovered_at=source[4],
                        )
                    )
    items = [
        InboxItem(
            id=row[0],
            user_id=row[1],
            canonical_url=row[2],
            title=row[3],
            excerpt=row[4],
            author=row[5],
            published_at=row[6],
            fetched_at=row[7],
            content_hash=row[8],
            status=row[9],
            sources=source_map[row[0]],
            created_at=row[10],
            updated_at=row[11],
        )
        for row in visible
    ]
    return items, len(rows) > bounded


def update_inbox_item_status_db(
    user_id: str,
    item_id: str,
    status: str,
) -> InboxItem | None:
    with get_conn() as conn:
        if not conn:
            raise InboxStoreUnavailable("database_unavailable")
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE inbox_items SET status = %s, updated_at = NOW()
                WHERE user_id = %s AND id = %s
                RETURNING id, user_id, canonical_url, title, excerpt, author,
                          published_at, fetched_at, content_hash, status,
                          created_at, updated_at
                """,
                (status, user_id, item_id),
            )
            row = cur.fetchone()
            sources = []
            if row:
                cur.execute(
                    """
                    SELECT subscription_id, source_name, feed_entry_id, discovered_at
                    FROM inbox_item_sources WHERE item_id = %s
                    ORDER BY discovered_at ASC
                    """,
                    (item_id,),
                )
                sources = [
                    InboxItemSource(
                        subscription_id=source[0],
                        source_name=source[1],
                        feed_entry_id=source[2],
                        discovered_at=source[3],
                    )
                    for source in cur.fetchall()
                ]
        conn.commit()
    if not row:
        return None
    return InboxItem(
        id=row[0], user_id=row[1], canonical_url=row[2], title=row[3],
        excerpt=row[4], author=row[5], published_at=row[6], fetched_at=row[7],
        content_hash=row[8], status=row[9], sources=sources,
        created_at=row[10], updated_at=row[11],
    )


def get_inbox_summary_db(user_id: str) -> InboxSummary:
    with get_conn() as conn:
        if not conn:
            raise InboxStoreUnavailable("database_unavailable")
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*), COUNT(*) FILTER (WHERE enabled),
                       MAX(last_refresh_at)
                FROM content_subscriptions WHERE user_id = %s
                """,
                (user_id,),
            )
            subscription_count, enabled_count, last_refresh_at = cur.fetchone()
            cur.execute(
                """
                SELECT COUNT(*) FILTER (WHERE status = 'unread'),
                       COUNT(*) FILTER (WHERE status = 'saved')
                FROM inbox_items WHERE user_id = %s
                """,
                (user_id,),
            )
            unread_count, saved_count = cur.fetchone()
            cur.execute(
                """
                SELECT last_refresh_status FROM content_subscriptions
                WHERE user_id = %s AND last_refresh_at IS NOT NULL
                ORDER BY last_refresh_at DESC LIMIT 1
                """,
                (user_id,),
            )
            latest = cur.fetchone()
    return InboxSummary(
        subscription_count=subscription_count,
        enabled_subscription_count=enabled_count,
        unread_count=unread_count,
        saved_count=saved_count,
        last_refresh_at=last_refresh_at,
        last_refresh_status=latest[0] if latest else None,
    )
