"""PostgreSQL adapter for statement ingestion metadata and settings."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from app.connectors.postgres.connection import get_conn

logger = logging.getLogger(__name__)

_RECORD_COLUMNS = """
    import_id, user_id, source_file, source_format, imported_count,
    status, error, sample, quality_report, ingestion_channel,
    content_hash, stored_path, detected_source, origin_key,
    origin_metadata, created_at, updated_at
"""


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
    ingestion_channel: str = "upload",
    content_hash: str = "",
    stored_path: str = "",
    detected_source: str = "",
    origin_key: str = "",
    origin_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Insert or update one durable ingestion record."""

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
        "ingestion_channel": ingestion_channel,
        "content_hash": content_hash,
        "stored_path": stored_path,
        "detected_source": detected_source,
        "origin_key": origin_key,
        "origin_metadata": origin_metadata or {},
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
                        imported_count, status, error, sample, quality_report,
                        ingestion_channel, content_hash, stored_path,
                        detected_source, origin_key, origin_metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (import_id) DO UPDATE SET
                        source_format = EXCLUDED.source_format,
                        imported_count = EXCLUDED.imported_count,
                        status = EXCLUDED.status,
                        error = EXCLUDED.error,
                        sample = EXCLUDED.sample,
                        quality_report = EXCLUDED.quality_report,
                        ingestion_channel = EXCLUDED.ingestion_channel,
                        content_hash = EXCLUDED.content_hash,
                        stored_path = EXCLUDED.stored_path,
                        detected_source = EXCLUDED.detected_source,
                        origin_key = EXCLUDED.origin_key,
                        origin_metadata = EXCLUDED.origin_metadata,
                        updated_at = NOW()
                    RETURNING created_at, updated_at
                    """,
                    (
                        record["import_id"], user_id, source_file, source_format,
                        imported_count, status, error,
                        json.dumps(record["sample"], ensure_ascii=False),
                        json.dumps(record["quality_report"], ensure_ascii=False),
                        ingestion_channel, content_hash, stored_path,
                        detected_source, origin_key,
                        json.dumps(record["origin_metadata"], ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return {
                **record,
                "created_at": row[0].isoformat() if row else None,
                "updated_at": row[1].isoformat() if row else None,
            }
        except Exception:
            conn.rollback()
            logger.exception("Failed to save statement import record user=%s", user_id)
            return None


def get_statement_import_record_db(import_id: str) -> dict[str, Any] | None:
    return _fetch_one(f"SELECT {_RECORD_COLUMNS} FROM statement_import_records WHERE import_id = %s", (import_id,))


def get_statement_import_by_hash_db(user_id: str, content_hash: str) -> dict[str, Any] | None:
    if not content_hash:
        return None
    return _fetch_one(
        f"SELECT {_RECORD_COLUMNS} FROM statement_import_records WHERE user_id = %s AND content_hash = %s ORDER BY created_at DESC LIMIT 1",
        (user_id, content_hash),
    )


def list_statement_import_records_db(
    user_id: str,
    limit: int = 10,
    status: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [user_id]
    where = "WHERE user_id = %s"
    if status:
        where += " AND status = %s"
        params.append(status)
    params.append(max(1, min(limit, 100)))
    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_RECORD_COLUMNS} FROM statement_import_records {where} ORDER BY created_at DESC LIMIT %s",
                    tuple(params),
                )
                rows = cur.fetchall()
            return [_row_to_record(row) for row in rows]
        except Exception:
            logger.exception("Failed to list statement import records user=%s", user_id)
            return []


def get_latest_statement_import_record_db(user_id: str) -> dict[str, Any] | None:
    rows = list_statement_import_records_db(user_id=user_id, limit=1)
    return rows[0] if rows else None


def list_latest_quality_reports_db(user_id: str) -> list[dict[str, Any]]:
    """Latest successful quality report per source, for agent evidence."""

    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (
                               COALESCE(NULLIF(detected_source, ''), source_format)
                           )
                           COALESCE(NULLIF(detected_source, ''), source_format),
                           quality_report, created_at
                    FROM statement_import_records
                    WHERE user_id = %s AND status = 'succeeded'
                          AND quality_report <> '{}'::jsonb
                    ORDER BY COALESCE(NULLIF(detected_source, ''), source_format),
                             created_at DESC
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


def get_statement_import_settings_db(user_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        if not conn:
            return _default_settings(user_id)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, folder_enabled, folder_subdirectory,
                           auto_commit, email_enabled, email_mailbox,
                           email_allowed_senders, updated_at
                    FROM statement_import_settings WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
            return _settings_row(row) if row else _default_settings(user_id)
        except Exception:
            logger.exception("Failed to read statement settings user=%s", user_id)
            return _default_settings(user_id)


def save_statement_import_settings_db(user_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    settings = {**_default_settings(user_id), **payload, "user_id": user_id}
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO statement_import_settings (
                        user_id, folder_enabled, folder_subdirectory,
                        auto_commit, email_enabled, email_mailbox,
                        email_allowed_senders
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (user_id) DO UPDATE SET
                        folder_enabled = EXCLUDED.folder_enabled,
                        folder_subdirectory = EXCLUDED.folder_subdirectory,
                        auto_commit = EXCLUDED.auto_commit,
                        email_enabled = EXCLUDED.email_enabled,
                        email_mailbox = EXCLUDED.email_mailbox,
                        email_allowed_senders = EXCLUDED.email_allowed_senders,
                        updated_at = NOW()
                    RETURNING user_id, folder_enabled, folder_subdirectory,
                              auto_commit, email_enabled, email_mailbox,
                              email_allowed_senders, updated_at
                    """,
                    (
                        user_id, settings["folder_enabled"],
                        settings["folder_subdirectory"], settings["auto_commit"],
                        settings["email_enabled"], settings["email_mailbox"],
                        json.dumps(settings["email_allowed_senders"], ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return _settings_row(row)
        except Exception:
            conn.rollback()
            logger.exception("Failed to save statement settings user=%s", user_id)
            return None


def list_statement_import_settings_db() -> list[dict[str, Any]]:
    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, folder_enabled, folder_subdirectory,
                           auto_commit, email_enabled, email_mailbox,
                           email_allowed_senders, updated_at
                    FROM statement_import_settings
                    WHERE folder_enabled OR email_enabled
                    """
                )
                rows = cur.fetchall()
            return [_settings_row(row) for row in rows]
        except Exception:
            logger.exception("Failed to list statement import settings")
            return []


def _fetch_one(query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
            return _row_to_record(row) if row else None
        except Exception:
            logger.exception("Failed to read statement import record")
            return None


def _row_to_record(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "import_id": row[0], "user_id": row[1], "source_file": row[2],
        "source_format": row[3], "imported_count": row[4], "status": row[5],
        "error": row[6], "sample": row[7], "quality_report": row[8],
        "ingestion_channel": row[9], "content_hash": row[10],
        "stored_path": row[11], "detected_source": row[12],
        "origin_key": row[13], "origin_metadata": row[14],
        "created_at": row[15].isoformat(), "updated_at": row[16].isoformat(),
    }


def _default_settings(user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "folder_enabled": True,
        "folder_subdirectory": "",
        "auto_commit": True,
        "email_enabled": False,
        "email_mailbox": "INBOX",
        "email_allowed_senders": [],
        "updated_at": None,
    }


def _settings_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "user_id": row[0], "folder_enabled": row[1],
        "folder_subdirectory": row[2], "auto_commit": row[3],
        "email_enabled": row[4], "email_mailbox": row[5],
        "email_allowed_senders": row[6] or [],
        "updated_at": row[7].isoformat() if row[7] else None,
    }
