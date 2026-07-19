from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.connectors.postgres import exchange_rate_store
from app.models.costing import ExchangeRateSnapshot


class FakeCursor:
    def __init__(self, row=None):
        self.row = row
        self.query = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query, params):
        self.query = query
        self.params = params

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


def _conn_context(connection):
    @contextmanager
    def fake_get_conn():
        yield connection

    return fake_get_conn


def test_identity_rate_needs_no_database(monkeypatch):
    @contextmanager
    def should_not_connect():
        raise AssertionError("identity conversion must not query postgres")
        yield

    monkeypatch.setattr(exchange_rate_store, "get_conn", should_not_connect)

    snapshot = exchange_rate_store.get_exchange_rate_snapshot_db(
        "usd", "USD", date(2026, 7, 13)
    )

    assert snapshot.exchange_rate == Decimal("1")
    assert snapshot.exchange_rate_source == "identity"


def test_latest_snapshot_query_is_bounded_by_accounting_date(monkeypatch):
    connection = FakeConnection(
        row=("USD", "CNY", Decimal("7.2"), date(2026, 7, 9), "test-fx")
    )
    monkeypatch.setattr(
        exchange_rate_store, "get_conn", _conn_context(connection)
    )

    snapshot = exchange_rate_store.get_exchange_rate_snapshot_db(
        "USD", "CNY", date(2026, 7, 10)
    )

    assert snapshot.exchange_rate_date == date(2026, 7, 9)
    assert "exchange_rate_date <= %s" in connection.cursor_instance.query
    assert connection.cursor_instance.params == ("USD", "CNY", date(2026, 7, 10))


def test_snapshot_save_uses_immutable_conflict_rule(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        exchange_rate_store, "get_conn", _conn_context(connection)
    )
    snapshot = ExchangeRateSnapshot(
        billing_currency="USD",
        reporting_currency="CNY",
        exchange_rate="7.2",
        exchange_rate_date="2026-07-09",
        exchange_rate_source="test-fx",
    )

    assert exchange_rate_store.save_exchange_rate_snapshot_db(snapshot) is True
    assert "DO NOTHING" in connection.cursor_instance.query
    assert connection.committed is True


def test_invalid_snapshot_is_rejected_before_persistence():
    with pytest.raises(ValidationError):
        ExchangeRateSnapshot(
            billing_currency="US",
            reporting_currency="CNY",
            exchange_rate="0",
            exchange_rate_date="2026-07-09",
            exchange_rate_source="test-fx",
        )
