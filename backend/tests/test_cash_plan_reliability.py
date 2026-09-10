from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from app.connectors.postgres import cash_plan_store
from app.connectors.postgres.cash_plan_store import CashPlanStorageError
from app.models.cash_plan import CashPlanUpdate
from app.routes import cash_plan as route
from app.services import cash_plan as service


def test_missing_plan_stays_unconfigured_instead_of_becoming_zero(monkeypatch):
    monkeypatch.setattr(service, "get_cash_plan_db", lambda user_id: None)

    assert service.get_cash_plan("new-user") is None
    assert service.cash_plan_context("new-user") == {
        "available": True,
        "configured": False,
        "plan": None,
        "projection": None,
    }


def test_optional_cfo_context_marks_storage_failure_without_inventing_amounts(monkeypatch):
    def fail(_user_id):
        raise CashPlanStorageError("database offline")

    monkeypatch.setattr(service, "get_cash_plan_db", fail)

    assert service.cash_plan_context("demo") == {
        "available": False,
        "configured": False,
        "plan": None,
        "projection": None,
    }


def test_cash_plan_route_returns_an_explicit_unconfigured_contract(monkeypatch):
    monkeypatch.setattr(route, "get_cash_plan", lambda user_id: None)

    result = route.read_cash_plan("new-user", horizon_days=120)

    assert result == {"configured": False, "plan": None, "projection": None}


def test_cash_plan_route_returns_503_when_storage_fails(monkeypatch):
    def fail(_user_id):
        raise CashPlanStorageError("database offline")

    monkeypatch.setattr(route, "get_cash_plan", fail)

    with pytest.raises(HTTPException) as exc:
        route.read_cash_plan("demo", horizon_days=120)

    assert exc.value.status_code == 503
    assert exc.value.detail == "Cash plan is temporarily unavailable"


def test_cash_plan_write_failure_is_not_reported_as_saved(monkeypatch):
    def fail(_user_id, _request):
        raise CashPlanStorageError("write failed")

    monkeypatch.setattr(route, "update_cash_plan", fail)

    with pytest.raises(HTTPException) as exc:
        route.write_cash_plan("demo", CashPlanUpdate())

    assert exc.value.status_code == 503
    assert exc.value.detail == "Cash plan could not be saved"


def test_store_treats_missing_database_connection_as_an_error(monkeypatch):
    @contextmanager
    def unavailable_connection():
        yield None

    monkeypatch.setattr(cash_plan_store, "get_conn", unavailable_connection)

    with pytest.raises(CashPlanStorageError):
        cash_plan_store.get_cash_plan_db("demo")
