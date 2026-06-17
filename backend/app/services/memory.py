"""
Conversation memory with PostgreSQL persistence and in-memory cache.
"""

import logging
from collections import defaultdict

from app.repositories.chat_repo import clear_history_db, get_chat_history_db, save_message_db

logger = logging.getLogger(__name__)

MAX_HISTORY = 50
_history: dict[str, list[dict]] = defaultdict(list)
_loaded_from_db: set[str] = set()


def get_chat_history(user_id: str, limit: int = MAX_HISTORY) -> list[dict]:
    if user_id not in _loaded_from_db:
        db_history = get_chat_history_db(user_id, limit)
        if db_history:
            _history[user_id] = db_history
        _loaded_from_db.add(user_id)
    return _history[user_id][-limit:]


def save_message(user_id: str, role: str, content: str) -> None:
    _history[user_id].append({"role": role, "content": content})
    if len(_history[user_id]) > MAX_HISTORY:
        _history[user_id] = _history[user_id][-MAX_HISTORY:]
    save_message_db(user_id, role, content)


def clear_history(user_id: str) -> None:
    _history[user_id] = []
    _loaded_from_db.discard(user_id)
    clear_history_db(user_id)
