from contextlib import contextmanager
from datetime import datetime, timezone

from app.connectors.postgres import investment_research_store


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, *, rows=None, fetchone_values=None):
        self.rows = rows or []
        self.fetchone_values = list(fetchone_values or [])
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query, params):
        self.executions.append((query, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.fetchone_values.pop(0) if self.fetchone_values else None


class FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class FakeConnection:
    def __init__(self, *, rows=None, fetchone_values=None):
        self.cursor_instance = FakeCursor(
            rows=rows,
            fetchone_values=fetchone_values,
        )
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


def test_watchlist_reads_are_user_scoped_and_bounded(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        investment_research_store,
        "get_conn",
        _conn_context(connection),
    )

    investment_research_store.list_watchlist_items_db("demo", 999)

    query, params = connection.cursor_instance.executions[0]
    assert "WHERE user_id = %s" in query
    assert params == ("demo", 100)


def test_scenario_detail_queries_scenario_and_positions_by_same_user(monkeypatch):
    scenario_row = (
        "demo",
        "scenario-1",
        "Research",
        "CNY",
        None,
        NOW,
        NOW,
    )
    connection = FakeConnection(
        rows=[("demo", "scenario-1", "AAPL", "equity", 2, NOW, NOW)],
        fetchone_values=[scenario_row],
    )
    monkeypatch.setattr(
        investment_research_store,
        "get_conn",
        _conn_context(connection),
    )

    detail = investment_research_store.get_investment_scenario_db(
        "demo",
        "scenario-1",
    )

    assert detail.scenario.user_id == "demo"
    assert detail.positions[0].symbol == "AAPL"
    assert all(
        params[:2] == ("demo", "scenario-1")
        for _, params in connection.cursor_instance.executions
    )


def test_replace_positions_checks_user_scoped_scenario_before_delete(monkeypatch):
    connection = FakeConnection(fetchone_values=[None])
    monkeypatch.setattr(
        investment_research_store,
        "get_conn",
        _conn_context(connection),
    )

    saved = investment_research_store.replace_scenario_positions_db(
        "other-user",
        "scenario-1",
        [{"symbol": "AAPL", "asset_type": "equity", "quantity": "1"}],
    )

    assert saved is False
    assert len(connection.cursor_instance.executions) == 1
    query, params = connection.cursor_instance.executions[0]
    assert "SELECT 1 FROM investment_scenarios" in query
    assert params == ("other-user", "scenario-1")
