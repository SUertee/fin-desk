from contextlib import contextmanager
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.connectors.postgres import profile_store
from app.models.user import CostReportingPreferences, ProfileUpdateRequest, UserProfile
from app.services import user_store


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


def _connection(connection):
    @contextmanager
    def fake_get_conn():
        yield connection

    return fake_get_conn


def test_cost_preferences_normalize_currency_and_reject_negative_budget():
    preferences = CostReportingPreferences(
        reporting_currency="cny", monthly_ai_budget="300.50"
    )
    assert preferences.reporting_currency == "CNY"
    assert preferences.monthly_ai_budget == Decimal("300.50")

    with pytest.raises(ValidationError):
        CostReportingPreferences(
            reporting_currency="USD", monthly_ai_budget="-1"
        )


def test_user_store_updates_cost_preferences_independently(monkeypatch):
    profile = UserProfile(user_id="demo")
    saved = []
    monkeypatch.setattr(user_store, "get_profile", lambda _: profile)
    monkeypatch.setattr(user_store, "save_profile_db", lambda value: saved.append(value))

    updated = user_store.update_profile(
        "demo",
        ProfileUpdateRequest(
            cost_preferences={
                "reporting_currency": "AUD",
                "monthly_ai_budget": "50",
            }
        ),
    )

    assert updated.preferences.response_tone == "balanced"
    assert updated.cost_preferences.reporting_currency == "AUD"
    assert updated.cost_preferences.monthly_ai_budget == Decimal("50")
    assert saved == [updated]


def test_profile_store_round_trips_cost_preferences(monkeypatch):
    row = (
        "demo",
        "Ryan",
        "Engineer",
        [],
        "moderate",
        0,
        0,
        0,
        0,
        0,
        0,
        "",
        {},
        {"reporting_currency": "CNY", "monthly_ai_budget": "300"},
    )
    read_connection = FakeConnection(row=row)
    monkeypatch.setattr(
        profile_store, "get_conn", _connection(read_connection)
    )

    loaded = profile_store.get_profile_db("demo")
    assert loaded.cost_preferences.reporting_currency == "CNY"
    assert loaded.cost_preferences.monthly_ai_budget == Decimal("300")

    write_connection = FakeConnection()
    monkeypatch.setattr(
        profile_store, "get_conn", _connection(write_connection)
    )
    assert profile_store.save_profile_db(loaded) is True
    assert "cost_preferences" in write_connection.cursor_instance.query
    assert '"monthly_ai_budget": "300"' in write_connection.cursor_instance.params[-2]

