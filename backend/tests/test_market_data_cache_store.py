from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from app.connectors.postgres import market_data_cache_store
from app.models.market_data import MarketCacheEntry


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


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
        market_data_cache_store,
        "get_conn",
        _connection_context(connection),
    )

    assert market_data_cache_store.get_market_data_cache_db("a" * 64, now=NOW) is None
    query, params = connection.cursor_instance.executions[0]
    assert "expires_at > %s" in query
    assert params == ("a" * 64, NOW)


def test_cache_upsert_uses_normalized_json(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        market_data_cache_store,
        "get_conn",
        _connection_context(connection),
    )
    entry = MarketCacheEntry(
        cache_key="b" * 64,
        operation="quote",
        provider="yfinance",
        payload={"quotes": []},
        fetched_at=NOW,
        expires_at=NOW + timedelta(minutes=3),
    )

    assert market_data_cache_store.save_market_data_cache_db(entry) is True
    query, params = connection.cursor_instance.executions[0]
    assert "ON CONFLICT (cache_key) DO UPDATE" in query
    assert params[0] == "b" * 64
    assert connection.committed is True
