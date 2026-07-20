from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from app.connectors.postgres import web_research_cache_store
from app.models.web_research import WebResearchCacheEntry


NOW = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, row=None):
        self.row = row
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query, params):
        self.executions.append((query, params))

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row=None):
        self.cursor_instance = FakeCursor(row)
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True


def _connection_context(connection):
    @contextmanager
    def fake_get_conn():
        yield connection

    return fake_get_conn


def test_cache_read_enforces_expiry_in_query(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        web_research_cache_store,
        "get_conn",
        _connection_context(connection),
    )

    assert web_research_cache_store.get_web_research_cache_db("a" * 64, now=NOW) is None
    query, params = connection.cursor_instance.executions[0]
    assert "expires_at > %s" in query
    assert params == ("a" * 64, NOW)


def test_cache_upsert_uses_normalized_json(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        web_research_cache_store,
        "get_conn",
        _connection_context(connection),
    )
    entry = WebResearchCacheEntry(
        cache_key="b" * 64,
        provider="tavily",
        payload={"status": "available"},
        fetched_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )

    assert web_research_cache_store.save_web_research_cache_db(entry) is True
    query, params = connection.cursor_instance.executions[0]
    assert "ON CONFLICT (cache_key) DO UPDATE" in query
    assert params[0] == "b" * 64
    assert connection.committed is True
