from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.connectors.postgres import investment_store
from app.models.investments import InvestmentPosition, MarketInstrument, MarketQuote


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query, params):
        self.executions.append((query, params))

    def fetchall(self):
        return self.rows


class FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class FakeConnection:
    def __init__(self, rows=None):
        self.cursor_instance = FakeCursor(rows)
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def transaction(self):
        return FakeTransaction()

    def commit(self):
        self.committed = True


def _conn_context(connection):
    @contextmanager
    def fake_get_conn():
        yield connection

    return fake_get_conn


def test_position_reads_are_user_scoped_and_bounded(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        investment_store, "get_conn", _conn_context(connection)
    )

    investment_store.list_investment_positions_db("demo", 900)

    query, params = connection.cursor_instance.executions[0]
    assert "WHERE user_id = %s" in query
    assert params == ("demo", 500)


def test_replace_positions_rejects_cross_user_data_before_database():
    position = InvestmentPosition(
        user_id="other-user",
        account_id="broker-1",
        symbol="AAPL",
        asset_type="equity",
        quantity="1",
        as_of=NOW,
    )

    with pytest.raises(ValueError, match="requested user and account"):
        investment_store.replace_investment_positions_db(
            "demo", "broker-1", [position]
        )


def test_quote_save_is_immutable(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        investment_store, "get_conn", _conn_context(connection)
    )
    quote = MarketQuote(
        symbol="AAPL",
        asset_type="equity",
        price={"amount": "200", "currency": "USD"},
        quote_as_of=NOW,
        source="recorded-test-feed",
    )

    assert investment_store.save_market_quote_snapshot_db(quote) is True
    query, _ = connection.cursor_instance.executions[0]
    assert "DO NOTHING" in query
    assert connection.committed is True


def test_latest_quote_lookup_is_as_of_bounded(monkeypatch):
    connection = FakeConnection(
        rows=[
            (
                "AAPL",
                "equity",
                Decimal("200"),
                "USD",
                NOW,
                "recorded-test-feed",
                "NASDAQ",
            )
        ]
    )
    monkeypatch.setattr(
        investment_store, "get_conn", _conn_context(connection)
    )

    quotes = investment_store.list_latest_market_quotes_db(
        [MarketInstrument(symbol="AAPL", asset_type="equity")],
        as_of=NOW,
    )

    query, params = connection.cursor_instance.executions[0]
    assert "q.quote_as_of <= %s" in query
    assert params == ["AAPL", "equity", NOW]
    assert quotes[0].price.amount == Decimal("200")
