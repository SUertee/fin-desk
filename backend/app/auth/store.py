"""PostgreSQL storage for opaque login sessions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.connectors.postgres.connection import get_conn

logger = logging.getLogger(__name__)


def create_session_db(
    *, token_hash: str, user_id: str, email: str, csrf_token: str, expires_at: datetime
) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO auth_sessions (
                        token_hash, user_id, email, csrf_token, expires_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (token_hash, user_id, email, csrf_token, expires_at),
                )
                cur.execute(
                    """
                    DELETE FROM auth_sessions
                    WHERE expires_at <= NOW()
                       OR (revoked_at IS NOT NULL AND revoked_at < NOW() - INTERVAL '1 day')
                    """
                )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to create authentication session")
            return False


def get_session_db(token_hash: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, email, csrf_token, expires_at
                    FROM auth_sessions
                    WHERE token_hash = %s
                      AND revoked_at IS NULL
                      AND expires_at > NOW()
                    """,
                    (token_hash,),
                )
                row = cur.fetchone()
            if not row:
                return None
            return {
                "user_id": row[0],
                "email": row[1],
                "csrf_token": row[2],
                "expires_at": row[3],
            }
        except Exception:
            logger.exception("Failed to read authentication session")
            return None


def revoke_session_db(token_hash: str) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE auth_sessions SET revoked_at = %s
                    WHERE token_hash = %s AND revoked_at IS NULL
                    """,
                    (datetime.now(timezone.utc), token_hash),
                )
                changed = cur.rowcount > 0
            conn.commit()
            return changed
        except Exception:
            logger.exception("Failed to revoke authentication session")
            return False
