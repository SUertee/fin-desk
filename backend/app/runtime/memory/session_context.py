"""Session memory read/write helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.connectors.postgres.memory_store import (
    get_session_memory_db,
    save_session_memory_db,
)


_in_process_memory: dict[tuple[str, str], dict[str, Any]] = {}


def _normalize_session_id(session_id: str) -> str:
    """Empty means the legacy flat-history scope; both map to "default"."""

    return (session_id or "").strip() or "default"


def read_session_context(user_id: str, session_id: str = "default") -> dict[str, Any] | None:
    if not user_id:
        return None
    session_id = _normalize_session_id(session_id)
    payload = get_session_memory_db(user_id, session_id)
    if payload:
        _in_process_memory[(user_id, session_id)] = dict(payload)
        return dict(payload)
    return _in_process_memory.get((user_id, session_id))


def write_session_context(
    *,
    user_id: str,
    session_id: str = "default",
    last_topic: dict[str, Any] | None = None,
    last_entities: list[dict[str, Any]] | None = None,
    last_result_brief: str | None = None,
    last_time_range: dict[str, Any] | None = None,
    last_query: dict[str, Any] | None = None,
    conversation_summary: str | None = None,
) -> dict[str, Any]:
    session_id = _normalize_session_id(session_id)
    existing = read_session_context(user_id, session_id) or {}
    if last_topic is not None:
        existing["last_topic"] = dict(last_topic)
    if last_entities is not None:
        existing["last_entities"] = list(last_entities)
    if last_result_brief:
        existing["last_result_brief"] = str(last_result_brief)[:600]
    if last_time_range is not None:
        existing["last_time_range"] = dict(last_time_range)
    # Truthy-only write: a run with no typed query must never erase the
    # previous useful last_query with an empty object.
    if last_query:
        existing["last_query"] = dict(last_query)
    if conversation_summary:
        existing["conversation_summary"] = str(conversation_summary)[:1200]
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    _in_process_memory[(user_id, session_id)] = dict(existing)
    save_session_memory_db(user_id, existing, session_id)
    return existing


def reset_in_process_memory_for_test() -> None:
    _in_process_memory.clear()
