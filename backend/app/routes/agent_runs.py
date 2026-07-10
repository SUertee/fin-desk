"""Agent run endpoints for observability, replay, and debugging."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.evals.replay_run import replay_agent_run
from app.connectors.postgres.run_ledger_store import (
    get_agent_run_record_db,
    list_agent_run_records_db,
)
from app.runtime.observability.trace_projector import project_run_record

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.get("/user/{user_id}")
def list_agent_runs(
    user_id: str,
    limit: int = 20,
    offset: int = 0,
    entrypoint: str | None = None,
    runtime_used: str | None = None,
    audit_status: str | None = None,
    has_error: bool | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
):
    try:
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)
        rows = list_agent_run_records_db(
            user_id=user_id,
            limit=safe_limit + 1,
            offset=safe_offset,
            entrypoint=entrypoint,
            runtime_used=runtime_used,
            audit_status=audit_status,
            has_error=has_error,
            created_from=created_from,
            created_to=created_to,
        )
        has_more = len(rows) > safe_limit
        runs = rows[:safe_limit]
        return {
            "ok": True,
            "user_id": user_id,
            "pagination": {
                "limit": safe_limit,
                "offset": safe_offset,
                "has_more": has_more,
                "next_offset": safe_offset + safe_limit if has_more else None,
                "previous_offset": max(0, safe_offset - safe_limit)
                if safe_offset > 0
                else None,
            },
            "filters": {
                "entrypoint": entrypoint,
                "runtime_used": runtime_used,
                "audit_status": audit_status,
                "has_error": has_error,
                "created_from": created_from,
                "created_to": created_to,
            },
            "runs": runs,
        }
    except Exception:
        logger.exception("Failed to list agent runs for user=%s", user_id)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to list agent run records"},
        )


@router.get("/{request_id}/replay")
def replay_agent_run_route(request_id: str, case_id: str | None = None):
    try:
        report = replay_agent_run(request_id, case_id=case_id)
        if not report.record_found:
            return JSONResponse(
                status_code=404,
                content=report.model_dump(mode="json"),
            )
        if report.error:
            return JSONResponse(
                status_code=400,
                content=report.model_dump(mode="json"),
            )
        return {"ok": True, "replay": report.model_dump(mode="json")}
    except Exception:
        logger.exception("Failed to replay agent run request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to replay agent run record"},
        )


@router.get("/{request_id}/projected")
def get_projected_agent_run(request_id: str):
    try:
        record = get_agent_run_record_db(request_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": "Agent run record not found"},
            )
        return {"ok": True, "projection": project_run_record(record)}
    except Exception:
        logger.exception("Failed to project agent run request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to project agent run record"},
        )


@router.get("/{request_id}")
def get_agent_run(request_id: str):
    try:
        record = get_agent_run_record_db(request_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": "Agent run record not found"},
            )
        return {"ok": True, "record": record}
    except Exception:
        logger.exception("Failed to retrieve agent run request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to retrieve agent run record"},
        )
