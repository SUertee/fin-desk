from contextlib import contextmanager

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
