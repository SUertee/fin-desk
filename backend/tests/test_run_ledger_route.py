import json

from fastapi.responses import JSONResponse

from app.evals.replay_run import ReplayRunReport
from app.routes import agent_runs


def _json_response_body(response: JSONResponse) -> dict:
    return json.loads(response.body.decode("utf-8"))


def test_get_agent_run_returns_record(monkeypatch):
    monkeypatch.setattr(
        agent_runs,
        "get_agent_run_record_db",
        lambda request_id: {"request_id": request_id, "entrypoint": "chat"},
    )

    result = agent_runs.get_agent_run("req-1")

    assert result == {
        "ok": True,
        "record": {"request_id": "req-1", "entrypoint": "chat"},
    }


def test_get_projected_agent_run_returns_projection(monkeypatch):
    monkeypatch.setattr(
        agent_runs,
        "get_agent_run_record_db",
        lambda request_id: {
            "request_id": request_id,
            "entrypoint": "chat",
            "user_id": "demo",
            "runtime_requested": "self_hosted",
            "runtime_used": "self_hosted",
            "latency_ms": 1.0,
        },
    )

    result = agent_runs.get_projected_agent_run("req-1")

    assert result["ok"] is True
    assert result["projection"]["summary"]["runtime_used"] == "self_hosted"


def test_get_agent_run_returns_404_when_missing(monkeypatch):
    monkeypatch.setattr(agent_runs, "get_agent_run_record_db", lambda request_id: None)

    result = agent_runs.get_agent_run("missing")

    assert result.status_code == 404
    assert _json_response_body(result)["error"] == "Agent run record not found"


def test_list_agent_runs_clamps_limit(monkeypatch):
    captured = {}

    def fake_list(
        user_id,
        limit,
        *,
        offset=0,
        entrypoint=None,
        runtime_used=None,
        audit_status=None,
        has_error=None,
        created_from=None,
        created_to=None,
    ):
        captured["user_id"] = user_id
        captured["limit"] = limit
        captured["offset"] = offset
        captured["entrypoint"] = entrypoint
        captured["runtime_used"] = runtime_used
        captured["audit_status"] = audit_status
        captured["has_error"] = has_error
        captured["created_from"] = created_from
        captured["created_to"] = created_to
        return [{"request_id": "req-1"}, {"request_id": "req-2"}]

    monkeypatch.setattr(agent_runs, "list_agent_run_records_db", fake_list)

    result = agent_runs.list_agent_runs(
        "demo",
        limit=1_000,
        offset=10,
        entrypoint="chat",
        runtime_used="openai",
        audit_status="needs_review",
        has_error=False,
        created_from="2026-06-01T00:00:00Z",
        created_to="2026-06-17T23:59:59Z",
    )

    assert result == {
        "ok": True,
        "user_id": "demo",
        "pagination": {
            "limit": 100,
            "offset": 10,
            "has_more": False,
            "next_offset": None,
            "previous_offset": 0,
        },
        "filters": {
            "entrypoint": "chat",
            "runtime_used": "openai",
            "audit_status": "needs_review",
            "has_error": False,
            "created_from": "2026-06-01T00:00:00Z",
            "created_to": "2026-06-17T23:59:59Z",
        },
        "runs": [{"request_id": "req-1"}, {"request_id": "req-2"}],
    }
    assert captured == {
        "user_id": "demo",
        "limit": 101,
        "offset": 10,
        "entrypoint": "chat",
        "runtime_used": "openai",
        "audit_status": "needs_review",
        "has_error": False,
        "created_from": "2026-06-01T00:00:00Z",
        "created_to": "2026-06-17T23:59:59Z",
    }


def test_list_agent_runs_sets_next_offset_when_more_rows(monkeypatch):
    monkeypatch.setattr(
        agent_runs,
        "list_agent_run_records_db",
        lambda **kwargs: [
            {"request_id": "req-1"},
            {"request_id": "req-2"},
            {"request_id": "req-3"},
        ],
    )

    result = agent_runs.list_agent_runs("demo", limit=2, offset=4)

    assert result["runs"] == [{"request_id": "req-1"}, {"request_id": "req-2"}]
    assert result["pagination"] == {
        "limit": 2,
        "offset": 4,
        "has_more": True,
        "next_offset": 6,
        "previous_offset": 2,
    }


def test_replay_agent_run_route_returns_report(monkeypatch):
    monkeypatch.setattr(
        agent_runs,
        "replay_agent_run",
        lambda request_id, case_id=None: ReplayRunReport(
            request_id=request_id,
            record_found=True,
            case_id=case_id,
            record_summary={"request_id": request_id},
        ),
    )

    result = agent_runs.replay_agent_run_route("req-1", case_id="case-1")

    assert result["ok"] is True
    assert result["replay"]["request_id"] == "req-1"
    assert result["replay"]["case_id"] == "case-1"


def test_replay_agent_run_route_returns_404_for_missing_record(monkeypatch):
    monkeypatch.setattr(
        agent_runs,
        "replay_agent_run",
        lambda request_id, case_id=None: ReplayRunReport(
            request_id=request_id,
            record_found=False,
            error="Agent run record not found",
        ),
    )

    result = agent_runs.replay_agent_run_route("missing")

    assert result.status_code == 404
    assert _json_response_body(result)["error"] == "Agent run record not found"


def test_replay_agent_run_route_returns_400_for_bad_case(monkeypatch):
    monkeypatch.setattr(
        agent_runs,
        "replay_agent_run",
        lambda request_id, case_id=None: ReplayRunReport(
            request_id=request_id,
            record_found=True,
            case_id=case_id,
            error="Eval case not found: bad",
        ),
    )

    result = agent_runs.replay_agent_run_route("req-1", case_id="bad")

    assert result.status_code == 400
    assert _json_response_body(result)["error"] == "Eval case not found: bad"
