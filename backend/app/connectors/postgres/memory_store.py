"""PostgreSQL-backed session memory adapter."""

import json
import logging
from typing import Any

from app.connectors.postgres.connection import get_conn

logger = logging.getLogger(__name__)


def get_session_memory_db(user_id: str, session_id: str = "default") -> dict[str, Any] | None:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT memory
                    FROM session_memory
                    WHERE user_id = %s AND session_id = %s
                    """,
                    (user_id, session_id),
                )
                row = cur.fetchone()
            return row[0] if row else None
        except Exception:
            logger.exception("Failed to get session memory for user=%s", user_id)
            return None


def save_session_memory_db(
    user_id: str,
    memory: dict[str, Any],
    session_id: str = "default",
) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO session_memory (user_id, session_id, memory, updated_at)
                    VALUES (%s, %s, %s::jsonb, NOW())
                    ON CONFLICT (user_id, session_id)
                    DO UPDATE SET memory = EXCLUDED.memory, updated_at = NOW()
                    """,
                    (user_id, session_id, json.dumps(memory, ensure_ascii=False)),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to save session memory for user=%s", user_id)
            return False


def clear_session_memory_db(user_id: str, session_id: str = "default") -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM session_memory WHERE user_id = %s AND session_id = %s",
                    (user_id, session_id),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to clear session memory for user=%s", user_id)
            return False
