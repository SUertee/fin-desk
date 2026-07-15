from contextlib import contextmanager
from decimal import Decimal

from app.connectors.postgres import run_ledger_store
from app.models.runtime import AgentRunRecord


@contextmanager
def no_conn():
    yield None


def test_run_ledger_store_returns_safe_defaults_without_db(monkeypatch):
    monkeypatch.setattr(run_ledger_store, "get_conn", no_conn)
    record = AgentRunRecord(
        request_id="req-1",
        entrypoint="chat",
        user_id="demo",
        runtime_requested="openai",
        latency_ms=1.2,
    )

    assert run_ledger_store.save_agent_run_record_db(record) is False
    assert run_ledger_store.get_agent_run_record_db("req-1") is None
    assert run_ledger_store.list_agent_run_records_db("demo") == []


def test_historical_v1_record_is_normalized_once_at_repository_boundary():
    normalized = run_ledger_store.normalize_agent_run_record(
        {
            "schema_version": "agent-run-record/v1",
            "request_id": "legacy-1",
            "entrypoint": "chat",
            "user_id": "demo",
            "runtime_requested": "self_hosted",
            "latency_ms": 1.2,
            "cost": {
                "currency": "usd",
                "estimated_total_cost": 0.125,
            },
        }
    )

    assert normalized["schema_version"] == "agent-run-record/v2"
    assert normalized["cost"]["status"] == "partial"
    assert normalized["cost"]["issues"] == ["historical_v1_detail_unavailable"]
    assert normalized["cost"]["billing_totals"] == [
        {"amount": "0.125", "currency": "USD"}
    ]
    assert normalized["cost"]["reporting_total"] == {
        "amount": "0.125",
        "currency": "USD",
    }
    assert normalized["cost"]["stages"] == []


def test_invalid_historical_v1_cost_does_not_fabricate_zero_amount():
    normalized = run_ledger_store.normalize_agent_run_record(
        {
            "schema_version": "agent-run-record/v1",
            "request_id": "legacy-invalid-cost",
            "entrypoint": "chat",
            "user_id": "demo",
            "runtime_requested": "self_hosted",
            "latency_ms": 1.2,
            "cost": {
                "currency": "USD",
                "estimated_total_cost": "not-a-number",
            },
        }
    )

    assert normalized["cost"]["status"] == "partial"
    assert normalized["cost"]["billing_totals"] == []
    assert normalized["cost"]["reporting_total"] is None


def test_v2_record_round_trips_decimal_costs():
    record = AgentRunRecord(
        request_id="req-v2",
        entrypoint="chat",
        user_id="demo",
        runtime_requested="self_hosted",
        latency_ms=1.2,
        cost={
            "status": "complete",
            "reporting_currency": "CNY",
            "billing_totals": [{"amount": Decimal("0.0001"), "currency": "USD"}],
            "reporting_total": {"amount": Decimal("0.00072"), "currency": "CNY"},
        },
    )

    normalized = run_ledger_store.normalize_agent_run_record(
        record.model_dump(mode="json")
    )

    assert normalized["cost"]["billing_totals"][0]["amount"] == "0.0001"
    assert normalized["cost"]["reporting_total"]["amount"] == "0.00072"
