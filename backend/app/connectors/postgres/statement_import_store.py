"""PostgreSQL adapter for statement import metadata."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from app.connectors.postgres.connection import get_conn

logger = logging.getLogger(__name__)


def save_statement_import_record_db(
    *,
    user_id: str,
    source_file: str,
    source_format: str = "csv",
    imported_count: int = 0,
    status: str = "succeeded",
    error: str = "",
    sample: list[dict[str, Any]] | None = None,
    quality_report: dict[str, Any] | None = None,
    import_id: str | None = None,
) -> dict[str, Any] | None:
    record = {
        "import_id": import_id or f"imp_{uuid4().hex}",
        "user_id": user_id,
        "source_file": source_file,
        "source_format": source_format,
        "imported_count": imported_count,
        "status": status,
        "error": error,
        "sample": sample or [],
        "quality_report": quality_report or {},
    }
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO statement_import_records (
                        import_id, user_id, source_file, source_format,
                        imported_count, status, error, sample, quality_report
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    RETURNING created_at
                    """,
                    (
                        record["import_id"],
                        user_id,
                        source_file,
                        source_format,
                        imported_count,
                        status,
                        error,
                        json.dumps(record["sample"], ensure_ascii=False),
                        json.dumps(record["quality_report"], ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return {**record, "created_at": row[0].isoformat() if row else None}
        except Exception:
            logger.exception("Failed to save statement import record user=%s", user_id)
            return None


def list_latest_quality_reports_db(user_id: str) -> list[dict[str, Any]]:
    """Latest non-empty quality report per source, for agent evidence."""

    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (source_format)
                           source_format, quality_report, created_at
                    FROM statement_import_records
                    WHERE user_id = %s AND status = 'succeeded'
                          AND quality_report <> '{}'::jsonb
                    ORDER BY source_format, created_at DESC
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
            return [
                {
                    "source_type": row[0],
                    **(row[1] or {}),
                    "recorded_at": row[2].isoformat(),
                }
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list quality reports user=%s", user_id)
            return []


def list_statement_import_records_db(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT import_id, user_id, source_file, source_format,
                           imported_count, status, error, sample, created_at
                    FROM statement_import_records
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, max(1, min(limit, 100))),
                )
                rows = cur.fetchall()
            return [_row_to_record(row) for row in rows]
        except Exception:
            logger.exception("Failed to list statement import records user=%s", user_id)
            return []


def get_latest_statement_import_record_db(user_id: str) -> dict[str, Any] | None:
    rows = list_statement_import_records_db(user_id=user_id, limit=1)
    return rows[0] if rows else None


def _row_to_record(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "import_id": row[0],
        "user_id": row[1],
        "source_file": row[2],
        "source_format": row[3],
        "imported_count": row[4],
        "status": row[5],
        "error": row[6],
        "sample": row[7],
        "created_at": row[8].isoformat(),
    }
