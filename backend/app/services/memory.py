"""
Conversation memory with PostgreSQL persistence and in-memory cache.
"""

import logging
from collections import defaultdict

from app.connectors.postgres.chat_store import (
    clear_history_db,
    get_chat_history_db,
    save_message_db,
)

logger = logging.getLogger(__name__)

MAX_HISTORY = 50
_history: dict[str, list[dict]] = defaultdict(list)
_loaded_from_db: set[str] = set()


def _cache_key(user_id: str, session_id: str) -> str:
    return f"{user_id}::{session_id}"


def get_chat_history(
    user_id: str, limit: int = MAX_HISTORY, session_id: str = ""
) -> list[dict]:
    key = _cache_key(user_id, session_id)
    if key not in _loaded_from_db:
        db_history = get_chat_history_db(user_id, limit, session_id=session_id)
        if db_history:
            _history[key] = db_history
        _loaded_from_db.add(key)
    return _history[key][-limit:]


def save_message(
    user_id: str,
    role: str,
    content: str,
    session_id: str = "",
    request_id: str = "",
) -> None:
    key = _cache_key(user_id, session_id)
    _history[key].append({"role": role, "content": content})
    if len(_history[key]) > MAX_HISTORY:
        _history[key] = _history[key][-MAX_HISTORY:]
    save_message_db(user_id, role, content, session_id=session_id, request_id=request_id)


def clear_history(user_id: str) -> None:
    for key in [k for k in _history if k.startswith(f"{user_id}::")]:
        _history.pop(key, None)
        _loaded_from_db.discard(key)
    clear_history_db(user_id)
