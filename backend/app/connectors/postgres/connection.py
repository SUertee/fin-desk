"""PostgreSQL connector connection pool and schema initialization."""

import logging
from contextlib import contextmanager
from pathlib import Path

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_pool = None


def init_pool():
    """Create the connection pool and ensure schema exists."""
    global _pool
    if _pool is not None:
        return

    dsn = get_settings().database.dsn
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
    """Create tables and indexes from the checked-in schema file."""
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
