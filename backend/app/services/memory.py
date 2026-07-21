"""
Conversation memory with PostgreSQL persistence and Redis cache-aside.
"""

import logging
from collections import defaultdict

from app.connectors.cache.redis_cache import cache_scope, get_redis_cache
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


def _redis_key(user_id: str, session_id: str) -> str | None:
    cache = get_redis_cache()
    return cache.key("chat-history", user_id, session_id or "default") if cache else None


def get_chat_history(
    user_id: str, limit: int = MAX_HISTORY, session_id: str = ""
) -> list[dict]:
    key = _cache_key(user_id, session_id)
    cache = get_redis_cache()
    redis_key = _redis_key(user_id, session_id)
    if cache and redis_key:
        cached = cache.get_json(redis_key)
        if isinstance(cached, list):
            _history[key] = cached[-MAX_HISTORY:]
            _loaded_from_db.add(key)
            return _history[key][-limit:]

        db_history = get_chat_history_db(user_id, MAX_HISTORY, session_id=session_id)
        if db_history:
            _history[key] = db_history
        _loaded_from_db.add(key)
        history = _history[key][-MAX_HISTORY:]
        cache.set_json(
            redis_key,
            history,
            ttl_seconds=cache.settings.chat_history_ttl_seconds,
        )
        return history[-limit:]

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
    persisted = save_message_db(
        user_id,
        role,
        content,
        session_id=session_id,
        request_id=request_id,
    )
    cache = get_redis_cache()
    redis_key = _redis_key(user_id, session_id)
    if cache and redis_key:
        if persisted and key in _loaded_from_db:
            cache.set_json(
                redis_key,
                _history[key],
                ttl_seconds=cache.settings.chat_history_ttl_seconds,
            )
        else:
            cache.delete(redis_key)


def clear_history(user_id: str) -> None:
    for key in [k for k in _history if k.startswith(f"{user_id}::")]:
        _history.pop(key, None)
        _loaded_from_db.discard(key)
    clear_history_db(user_id)
    cache = get_redis_cache()
    if cache:
        cache.delete_matching(
            f"{cache.settings.key_prefix}:chat-history:{cache_scope(user_id)}:*"
        )
