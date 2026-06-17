"""
Database connection pool management and schema initialization.
"""

import logging
import os
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_pool = None


def init_pool():
    """Create the connection pool and ensure schema exists."""
    global _pool
    if _pool is not None:
        return

    dsn = os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL", "")
    if not dsn:
        logger.warning("No POSTGRES_DSN or DATABASE_URL set — database disabled")
        return

    try:
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(dsn, min_size=2, max_size=10, open=True)
        with _pool.connection() as conn:
            _ensure_schema(conn)
        logger.info("Database pool initialized (min=2, max=10)")
    except Exception:
        logger.exception("Failed to initialize database pool")
        _pool = None


def close_pool():
    """Gracefully close the connection pool."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        logger.info("Database pool closed")


@contextmanager
def get_conn():
    """Yield a connection from the pool. Returns None-context if pool unavailable."""
    if _pool is None:
        init_pool()
    if _pool is None:
        yield None
        return
    with _pool.connection() as conn:
        yield conn


def _ensure_schema(conn) -> None:
    """Create tables and indexes if they don't exist."""
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                occupation TEXT NOT NULL DEFAULT '',
                financial_goals JSONB NOT NULL DEFAULT '[]'::jsonb,
                risk_tolerance TEXT NOT NULL DEFAULT 'moderate',
                cash_balance DOUBLE PRECISION NOT NULL DEFAULT 0,
                savings DOUBLE PRECISION NOT NULL DEFAULT 0,
                investments DOUBLE PRECISION NOT NULL DEFAULT 0,
                liabilities DOUBLE PRECISION NOT NULL DEFAULT 0,
                monthly_income DOUBLE PRECISION NOT NULL DEFAULT 0,
                monthly_expenses DOUBLE PRECISION NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id BIGSERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_history_user_created_at
            ON chat_history (user_id, created_at DESC)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id BIGSERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                date DATE NOT NULL,
                month TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                counterparty TEXT NOT NULL DEFAULT '',
                amount DOUBLE PRECISION NOT NULL,
                gross_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'CNY',
                balance DOUBLE PRECISION,
                direction TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'other',
                status TEXT NOT NULL DEFAULT '',
                payment_method TEXT NOT NULL DEFAULT '',
                external_id TEXT NOT NULL DEFAULT '',
                merchant_order_id TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual',
                source_file TEXT NOT NULL DEFAULT '',
                source_format TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                is_duplicate BOOLEAN NOT NULL DEFAULT false,
                raw JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transactions_user_date
            ON transactions (user_id, date DESC, id DESC)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transactions_user_source_external
            ON transactions (user_id, source, external_id)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id BIGSERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                period_start DATE,
                period_end DATE,
                monthly_totals JSONB NOT NULL DEFAULT '[]'::jsonb,
                input JSONB NOT NULL DEFAULT '{}'::jsonb,
                output JSONB NOT NULL DEFAULT '{}'::jsonb,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created_at
            ON analysis_runs (user_id, created_at DESC, id DESC)
            """
        )
    conn.commit()
