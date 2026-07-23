"""Agent Hub integration endpoints: read-only projection contract."""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.integrations.agenthub import providers
from app.integrations.agenthub.router import router as agenthub_router
from app.runtime.capabilities.contracts import CapabilityRuntimeStatus
from app.runtime.capabilities.definitions import (
    SPECIALIST_CAPABILITY_DEFINITIONS,
    TOOL_CAPABILITY_DEFINITIONS,
)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("AGENTHUB_TOKEN", raising=False)
    app = FastAPI()
    app.include_router(agenthub_router)
    return TestClient(app)


def test_manifest_has_all_profile_facets(client):
    body = client.get("/agent-gateway/manifest").json()
    assert body["schema_version"] == "0.1"
    assert body["identity"]["agent_id"] == "personal-finance-cfo"
    assert body["identity"]["kind"] == "team"
    for facet in ("purpose", "capabilities", "policy", "resources",
                  "topology", "runtime", "state_ref"):
        assert facet in body, facet
    expected = len(TOOL_CAPABILITY_DEFINITIONS) + len(
        SPECIALIST_CAPABILITY_DEFINITIONS
    )
    assert len(body["capabilities"]) == expected
    assert body["control_tier_claims"] == [
        "catalogued", "observable", "invokable",
    ]


def test_roster_members_and_review_gate(client):
    body = client.get("/agent-gateway/roster").json()
    assert body["team_id"] == "personal-finance-cfo"
    assert body["supervisor"] == "cfo"
    member_ids = {m["id"] for m in body["members"]}
    assert member_ids == {
        "cfo", "expense_analyst", "budget_coach", "auditor",
        "market_context", "investment_research",
    }
    assert {"from": "auditor", "to": "*", "kind": "review_gate"} in body["edges"]
    delegations = [e for e in body["edges"] if e["kind"] == "delegation"]
    assert len(delegations) == len(SPECIALIST_CAPABILITY_DEFINITIONS)


def test_runs_projects_ledger_records(client, monkeypatch):
    summaries = [
        {"request_id": "req-2", "error_type": None,
         "created_at": "2026-07-22T10:05:00+00:00"},
        {"request_id": "req-1", "error_type": "ToolError",
         "created_at": "2026-07-22T10:00:00+00:00"},
    ]
    records = {
        "req-1": {"tool_calls": [
            {"name": "get_expense_snapshot", "status": "called"}], "handoffs": []},
        "req-2": {"tool_calls": [], "handoffs": [
            {"to_agent": "auditor", "status": "completed"}]},
    }
    monkeypatch.setattr(
        providers, "list_agent_run_records_db",
        lambda user_id, limit, **kw: list(summaries),
    )
    monkeypatch.setattr(
        providers, "get_agent_run_record_db", lambda rid: records.get(rid)
    )

    body = client.get("/agent-gateway/runs").json()
    assert body["cursor"] == "2026-07-22T10:05:00+00:00"
    assert [e["run_id"] for e in body["events"]] == ["req-1", "req-2"]

    failed = body["events"][0]
    assert failed["status"] == "failed"
    assert failed["steps"] == [
        {"label": "汇总支出结构", "kind": "tool", "done": True}
    ]
    audited = body["events"][1]
    assert audited["status"] == "completed"
    assert audited["steps"][0]["kind"] == "audit"


def test_runs_empty_ledger_keeps_cursor(client, monkeypatch):
    monkeypatch.setattr(
        providers, "list_agent_run_records_db", lambda user_id, limit, **kw: []
    )
    body = client.get("/agent-gateway/runs?since=abc").json()
    assert body == {"schema_version": "0.1", "cursor": "abc", "events": []}


def test_state_reports_capability_health(client, monkeypatch):
    class FakeHealth:
        async def vibe_market_data_status(self, **kw):
            return CapabilityRuntimeStatus(
                enabled=True, available=False, reason="MCP down",
                checked_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
            )

    monkeypatch.setattr(
        providers, "get_capability_health_service", lambda: FakeHealth()
    )
    monkeypatch.setattr(
        providers, "list_agent_run_records_db", lambda user_id, limit, **kw: []
    )
    body = client.get("/agent-gateway/state").json()
    assert body["online"] is True
    assert body["health"][0]["available"] is False
    assert body["health"][0]["reason"] == "MCP down"
    assert body["last_run_at"] is None


def test_agent_card_is_public_and_a2a_shaped(client):
    body = client.get("/.well-known/agent-card.json").json()
    assert body["id"] == "personal-finance-cfo"
    assert body["protocolVersion"]
    skill_ids = {s["id"] for s in body["skills"]}
    assert "spending_review" in skill_ids


def test_token_guards_gateway_endpoints(monkeypatch):
    monkeypatch.setenv("AGENTHUB_TOKEN", "s3cret")
    app = FastAPI()
    app.include_router(agenthub_router)
    client = TestClient(app)

    assert client.get("/agent-gateway/manifest").status_code == 401
    ok = client.get(
        "/agent-gateway/manifest", headers={"Authorization": "Bearer s3cret"}
    )
    assert ok.status_code == 200
    # discovery card stays public
    assert client.get("/.well-known/agent-card.json").status_code == 200
