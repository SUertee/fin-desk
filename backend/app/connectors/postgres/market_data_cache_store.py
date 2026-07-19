"""PostgreSQL TTL cache for normalized market-data responses."""

from __future__ import annotations

import logging
from datetime import datetime

from app.connectors.postgres.connection import get_conn
from app.models.market_data import MarketCacheEntry


logger = logging.getLogger(__name__)


def get_market_data_cache_db(
    cache_key: str,
    *,
    now: datetime,
) -> MarketCacheEntry | None:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT cache_key, operation, provider, payload,
                           fetched_at, expires_at
                    FROM market_data_cache
                    WHERE cache_key = %s AND expires_at > %s
                    """,
                    (cache_key, now),
                )
                row = cur.fetchone()
            if not row:
                return None
            return MarketCacheEntry(
                cache_key=row[0],
                operation=row[1],
                provider=row[2],
                payload=row[3],
                fetched_at=row[4],
                expires_at=row[5],
            )
        except Exception:
            logger.exception("Failed to read market data cache key=%s", cache_key)
            return None


def save_market_data_cache_db(entry: MarketCacheEntry | dict) -> bool:
    parsed = MarketCacheEntry.model_validate(entry)
    with get_conn() as conn:
        if not conn:
            return False
        try:
            from psycopg.types.json import Jsonb

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO market_data_cache (
                        cache_key, operation, provider, payload,
                        fetched_at, expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (cache_key) DO UPDATE SET
                        operation = EXCLUDED.operation,
                        provider = EXCLUDED.provider,
                        payload = EXCLUDED.payload,
                        fetched_at = EXCLUDED.fetched_at,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = NOW()
                    """,
                    (
                        parsed.cache_key,
                        parsed.operation,
                        parsed.provider,
                        Jsonb(parsed.payload),
                        parsed.fetched_at,
                        parsed.expires_at,
                    ),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to save market data cache key=%s", parsed.cache_key)
            return False
