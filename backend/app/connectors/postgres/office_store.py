"""PostgreSQL adapter for My Office sessions.

Sessions are a thin grouping layer: messages live in `chat_history`
(session_id / request_id columns), evidence lives in the run ledger.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.connectors.postgres.connection import get_conn

logger = logging.getLogger(__name__)

TITLE_MAX_CHARS = 24
PREVIEW_MAX_CHARS = 60


def create_session_db(
    user_id: str,
    *,
    title: str = "",
    session_id: str | None = None,
) -> dict[str, Any] | None:
    record_id = session_id or f"sess_{uuid4().hex}"
    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO office_sessions (id, user_id, title, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (record_id, user_id, title.strip(), now, now),
                )
            conn.commit()
            return {
                "id": record_id,
                "user_id": user_id,
                "title": title.strip(),
                "status": "active",
                "last_message_preview": "",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        except Exception:
            logger.exception("Failed to create office session user=%s", user_id)
            return None


def get_session_db(user_id: str, session_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, title, status, last_message_preview,
                           created_at, updated_at
                    FROM office_sessions
                    WHERE user_id = %s AND id = %s
                    """,
                    (user_id, session_id),
                )
                row = cur.fetchone()
            return _row_to_session(row) if row else None
        except Exception:
            logger.exception("Failed to get office session user=%s", user_id)
            return None


def list_sessions_db(
    user_id: str, *, include_archived: bool = False, limit: int = 50
) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if not conn:
            return []
        try:
            status_clause = "" if include_archived else "AND status = 'active'"
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, user_id, title, status, last_message_preview,
                           created_at, updated_at
                    FROM office_sessions
                    WHERE user_id = %s {status_clause}
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (user_id, max(1, min(limit, 200))),
                )
                rows = cur.fetchall()
            return [_row_to_session(row) for row in rows]
        except Exception:
            logger.exception("Failed to list office sessions user=%s", user_id)
            return []


def update_session_db(
    user_id: str,
    session_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    last_message_preview: str | None = None,
) -> bool:
    sets: list[str] = ["updated_at = %s"]
    params: list[Any] = [datetime.now(timezone.utc)]
    if title is not None:
        sets.append("title = %s")
        params.append(title.strip()[:TITLE_MAX_CHARS * 4])
    if status is not None:
        sets.append("status = %s")
        params.append(status)
    if last_message_preview is not None:
        sets.append("last_message_preview = %s")
        params.append(last_message_preview[:PREVIEW_MAX_CHARS])
    params.extend([user_id, session_id])
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE office_sessions SET {', '.join(sets)} WHERE user_id = %s AND id = %s",
                    params,
                )
                updated = cur.rowcount > 0
            conn.commit()
            return updated
        except Exception:
            logger.exception("Failed to update office session user=%s", user_id)
            return False


def list_session_messages_db(
    user_id: str, session_id: str, limit: int = 200
) -> list[dict[str, Any]]:
    """Session thread in chronological order, with run linkage."""

    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, role, content, request_id, created_at
                    FROM chat_history
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at ASC, id ASC
                    LIMIT %s
                    """,
                    (user_id, session_id, max(1, min(limit, 500))),
                )
                rows = cur.fetchall()
            return [
                {
                    "id": str(row[0]),
                    "role": row[1],
                    "content": row[2],
                    "request_id": row[3] or None,
                    "created_at": row[4].isoformat(),
                }
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list session messages user=%s", user_id)
            return []


def _row_to_session(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "user_id": row[1],
        "title": row[2],
        "status": row[3],
        "last_message_preview": row[4],
        "created_at": row[5].isoformat(),
        "updated_at": row[6].isoformat(),
    }
