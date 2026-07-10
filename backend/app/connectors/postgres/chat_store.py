"""PostgreSQL-backed storage adapter for chat history."""

import logging
from datetime import datetime, timezone

from app.connectors.postgres.connection import get_conn

logger = logging.getLogger(__name__)


def get_chat_history_db(
    user_id: str, limit: int = 50, session_id: str = ""
) -> list[dict]:
    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT role, content
                    FROM chat_history
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, session_id, limit),
                )
                rows = cur.fetchall()
            rows.reverse()
            return [{"role": row[0], "content": row[1]} for row in rows]
        except Exception:
            logger.exception("Failed to get chat history for user=%s", user_id)
            return []


def save_message_db(
    user_id: str,
    role: str,
    content: str,
    session_id: str = "",
    request_id: str = "",
) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_history (user_id, role, content, session_id, request_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (user_id, role, content, session_id, request_id, datetime.now(timezone.utc)),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to save message for user=%s", user_id)
            return False


def clear_history_db(user_id: str) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat_history WHERE user_id = %s", (user_id,))
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to clear history for user=%s", user_id)
            return False
