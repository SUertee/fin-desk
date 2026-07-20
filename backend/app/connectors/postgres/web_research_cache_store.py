"""PostgreSQL TTL cache for governed web-research responses."""

from __future__ import annotations

import logging
from datetime import datetime

from app.connectors.postgres.connection import get_conn
from app.models.web_research import WebResearchCacheEntry


logger = logging.getLogger(__name__)


def get_web_research_cache_db(
    cache_key: str,
    *,
    now: datetime,
) -> WebResearchCacheEntry | None:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT cache_key, provider, payload, fetched_at, expires_at
                    FROM web_research_cache
                    WHERE cache_key = %s AND expires_at > %s
                    """,
                    (cache_key, now),
                )
                row = cur.fetchone()
            if not row:
                return None
            return WebResearchCacheEntry(
                cache_key=row[0],
                provider=row[1],
                payload=row[2],
                fetched_at=row[3],
                expires_at=row[4],
            )
        except Exception:
            logger.exception("Failed to read web research cache key=%s", cache_key)
            return None


def save_web_research_cache_db(entry: WebResearchCacheEntry | dict) -> bool:
    parsed = WebResearchCacheEntry.model_validate(entry)
    with get_conn() as conn:
        if not conn:
            return False
        try:
            from psycopg.types.json import Jsonb

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO web_research_cache (
                        cache_key, provider, payload, fetched_at, expires_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (cache_key) DO UPDATE SET
                        provider = EXCLUDED.provider,
                        payload = EXCLUDED.payload,
                        fetched_at = EXCLUDED.fetched_at,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = NOW()
                    """,
                    (
                        parsed.cache_key,
                        parsed.provider,
                        Jsonb(parsed.payload),
                        parsed.fetched_at,
                        parsed.expires_at,
                    ),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception(
                "Failed to save web research cache key=%s", parsed.cache_key
            )
            return False
