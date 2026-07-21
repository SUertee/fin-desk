import json

import pytest

from app.config.settings import RedisSettings
from app.connectors.cache.redis_cache import RedisJsonCache
from app.runtime.memory import session_context
from app.services import memory as memory_service


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail = False

    def get(self, key: str):
        if self.fail:
            raise ConnectionError("cache unavailable")
        return self.values.get(key)

    def set(self, key: str, value: str, *, ex: int):
        if self.fail:
            raise ConnectionError("cache unavailable")
        self.values[key] = value
        self.ttls[key] = ex
        return True

    def delete(self, *keys: str):
        if self.fail:
            raise ConnectionError("cache unavailable")
        for key in keys:
            self.values.pop(key, None)
            self.ttls.pop(key, None)
        return len(keys)

    def scan_iter(self, *, match: str, count: int):
        del count
        prefix = match.removesuffix("*")
        return iter(key for key in self.values if key.startswith(prefix))

    def ping(self):
        if self.fail:
            raise ConnectionError("cache unavailable")
        return True

    def close(self):
        return None


@pytest.fixture
def cache():
    client = FakeRedisClient()
    settings = RedisSettings(
        url="redis://test:6379/0",
        chat_history_ttl_seconds=60,
        session_memory_ttl_seconds=120,
    )
    return RedisJsonCache(settings, client=client)


@pytest.fixture(autouse=True)
def reset_local_memory():
    memory_service._history.clear()
    memory_service._loaded_from_db.clear()
    session_context.reset_in_process_memory_for_test()
    yield


def test_redis_json_cache_uses_hashed_scopes_and_ttl(cache):
    key = cache.key("session-memory", "demo@example.com", "room-a")

    assert "demo@example.com" not in key
    assert cache.set_json(key, {"topic": "shopping"}, ttl_seconds=120) is True
    assert cache.get_json(key) == {"topic": "shopping"}
    assert cache._client.ttls[key] == 120


def test_redis_json_cache_fails_open(cache):
    cache._client.fail = True

    assert cache.get_json("missing") is None
    assert cache.set_json("key", {"value": 1}, ttl_seconds=60) is False
    assert cache.delete("key") is False
    assert cache.ping() is False


def test_chat_history_is_loaded_once_then_served_from_redis(monkeypatch, cache):
    db_calls = []
    monkeypatch.setattr(memory_service, "get_redis_cache", lambda: cache)
    monkeypatch.setattr(
        memory_service,
        "get_chat_history_db",
        lambda user_id, limit, session_id="": db_calls.append(session_id)
        or [{"role": "user", "content": "hello"}],
    )

    assert memory_service.get_chat_history("demo", session_id="room-a")[0][
        "content"
    ] == "hello"
    memory_service._history.clear()
    memory_service._loaded_from_db.clear()
    assert memory_service.get_chat_history("demo", session_id="room-a")[0][
        "content"
    ] == "hello"
    assert db_calls == ["room-a"]


def test_chat_write_refreshes_warm_cache(monkeypatch, cache):
    monkeypatch.setattr(memory_service, "get_redis_cache", lambda: cache)
    monkeypatch.setattr(
        memory_service,
        "get_chat_history_db",
        lambda *args, **kwargs: [{"role": "user", "content": "first"}],
    )
    monkeypatch.setattr(memory_service, "save_message_db", lambda *args, **kwargs: True)

    memory_service.get_chat_history("demo", session_id="room-a")
    memory_service.save_message(
        "demo", "assistant", "second", session_id="room-a"
    )

    key = cache.key("chat-history", "demo", "room-a")
    assert [item["content"] for item in json.loads(cache._client.values[key])] == [
        "first",
        "second",
    ]


def test_session_memory_uses_redis_and_postgres_remains_source(monkeypatch, cache):
    db_reads = []
    db_writes = []
    monkeypatch.setattr(session_context, "get_redis_cache", lambda: cache)
    monkeypatch.setattr(
        session_context,
        "get_session_memory_db",
        lambda user_id, session_id: db_reads.append(session_id)
        or {"conversation_summary": "from postgres"},
    )
    monkeypatch.setattr(
        session_context,
        "save_session_memory_db",
        lambda user_id, memory, session_id: db_writes.append(dict(memory)) or True,
    )

    assert session_context.read_session_context("demo", "room-a")[
        "conversation_summary"
    ] == "from postgres"
    session_context.reset_in_process_memory_for_test()
    assert session_context.read_session_context("demo", "room-a")[
        "conversation_summary"
    ] == "from postgres"
    assert db_reads == ["room-a"]

    updated = session_context.write_session_context(
        user_id="demo", session_id="room-a", last_result_brief="new brief"
    )
    assert db_writes[-1]["last_result_brief"] == "new brief"
    assert cache.get_json(cache.key("session-memory", "demo", "room-a")) == updated
