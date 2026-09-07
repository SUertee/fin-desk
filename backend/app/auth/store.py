"""PostgreSQL storage for opaque login sessions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.connectors.postgres.connection import get_conn

logger = logging.getLogger(__name__)


def owner_exists_db() -> bool | None:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM auth_users)")
                row = cur.fetchone()
            return bool(row and row[0])
        except Exception:
            logger.exception("Failed to check authentication owner")
            return None


def get_owner_by_email_db(email: str) -> dict[str, str] | None:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, email, password_hash
                    FROM auth_users WHERE email = %s
                    """,
                    (email.strip().lower(),),
                )
                row = cur.fetchone()
            if not row:
                return None
            return {"user_id": row[0], "email": row[1], "password_hash": row[2]}
        except Exception:
            logger.exception("Failed to read authentication owner")
            return None


def create_owner_db(*, user_id: str, email: str, password_hash: str) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO auth_users (
                        singleton, user_id, email, password_hash
                    ) VALUES (TRUE, %s, %s, %s)
                    """,
                    (user_id, email.strip().lower(), password_hash),
                )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            logger.warning("Initial owner registration was rejected")
            return False


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
