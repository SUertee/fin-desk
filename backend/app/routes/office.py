"""My Office endpoints: sessions, session messages, user evidence projection."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.connectors.postgres.office_store import (
    create_session_db,
    get_session_db,
    list_session_messages_db,
    list_sessions_db,
    update_session_db,
)
from app.connectors.postgres.run_ledger_store import get_agent_run_record_db
from app.connectors.postgres.statement_import_store import list_latest_quality_reports_db
from app.models.office import (
    AdvancedDetails,
    CreateSessionRequest,
    DataCoverage,
    EvidenceAudit,
    EvidenceFinding,
    OfficeMessage,
    OfficeSession,
    UpdateSessionRequest,
    UserEvidenceProjection,
)
from app.models.routing import ConversationRoute
from app.runtime.observability.steps_projection import project_steps
from app.services.memory import save_message

logger = logging.getLogger(__name__)
router = APIRouter()


def _project_message_route(request_id: str | None) -> ConversationRoute | None:
    """Expose only the product-safe route flags for a persisted assistant turn."""

    if not request_id:
        return None
    record = get_agent_run_record_db(request_id)
    if not record:
        return None
    raw_route = (record.get("policy") or {}).get("conversation_route")
    if not raw_route:
        return None
    try:
        return ConversationRoute.model_validate(raw_route)
    except Exception:
        logger.warning("Invalid conversation route in run record request_id=%s", request_id)
        return None


@router.post("/office/sessions", response_model=OfficeSession)
def create_session(req: CreateSessionRequest):
    try:
        title = req.title.strip()
        if not title and req.seed_messages:
            first_user = next(
                (m.content for m in req.seed_messages if m.role == "user"), ""
            )
            title = " ".join(first_user.split())[:24]
        session = create_session_db(req.user_id, title=title)
        if session is None:
            return JSONResponse(
                status_code=503,
                content={"ok": False, "error": "Session persistence unavailable"},
            )
        # Promote a floating-chat conversation: seeds persist in order but
        # carry no run linkage (they had none), so they render without
        # evidence chips — honest by design.
        for seed in req.seed_messages:
            save_message(req.user_id, seed.role, seed.content, session_id=session["id"])
        if req.seed_messages:
            last = req.seed_messages[-1].content
            update_session_db(
                req.user_id, session["id"], last_message_preview=last
            )
            session["last_message_preview"] = last[:60]
        return OfficeSession.model_validate(session)
    except Exception:
        logger.exception("Failed to create office session")
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to create session"})


@router.get("/office/sessions/{user_id}")
def list_sessions(user_id: str, include_archived: bool = False):
    try:
        sessions = list_sessions_db(user_id, include_archived=include_archived)
        return {"user_id": user_id, "sessions": sessions}
    except Exception:
        logger.exception("Failed to list office sessions user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to list sessions"})


@router.get("/office/sessions/{user_id}/{session_id}/messages")
def list_messages(user_id: str, session_id: str):
    try:
        if get_session_db(user_id, session_id) is None:
            return JSONResponse(
                status_code=404, content={"ok": False, "error": "Unknown session"}
            )
        messages = [
            OfficeMessage.model_validate(
                {**m, "route": _project_message_route(m.get("request_id"))}
            ).model_dump(mode="json")
            for m in list_session_messages_db(user_id, session_id)
        ]
        return {"session_id": session_id, "messages": messages}
    except Exception:
        logger.exception("Failed to list session messages user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to list messages"})


@router.patch("/office/sessions/{user_id}/{session_id}")
def update_session(user_id: str, session_id: str, req: UpdateSessionRequest):
    try:
        if get_session_db(user_id, session_id) is None:
            return JSONResponse(
                status_code=404, content={"ok": False, "error": "Unknown session"}
            )
        update_session_db(user_id, session_id, title=req.title, status=req.status)
        return {"ok": True, "session": get_session_db(user_id, session_id)}
    except Exception:
        logger.exception("Failed to update office session user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to update session"})


@router.get("/office/evidence/{request_id}", response_model=UserEvidenceProjection)
def get_evidence(request_id: str):
    """USER-layer evidence projection (`trace-observability.md`).

    Forbidden here by contract: latency, token usage, cost, model/provider
    names, confidence values, raw tool inputs/outputs.
    """

    try:
        record = get_agent_run_record_db(request_id)
        if record is None:
            return JSONResponse(
                status_code=404, content={"ok": False, "error": "Unknown run"}
            )
        user_id = str(record.get("user_id") or "")

        findings = []
        # Findings live in the composed response's data block if persisted;
        # fall back to observed handoff outputs.
        for handoff in record.get("handoffs") or []:
            output = handoff.get("output") or {}
            for finding in output.get("findings") or []:
                findings.append(
                    EvidenceFinding(
                        agent=str(output.get("specialist") or handoff.get("to_agent") or "cfo"),
                        title=str(finding.get("title") or ""),
                        evidence=[str(item) for item in finding.get("evidence") or []],
                    )
                )

        input_summary = record.get("input_summary") or {}
        quality_reports = list_latest_quality_reports_db(user_id) if user_id else []
        source_counts = {
            report.get("source_type", "unknown"): int(report.get("imported_count") or 0)
            for report in quality_reports
        }
        quality_warnings = [
            warning
            for report in quality_reports
            for warning in (report.get("warnings") or [])
        ][:3]

        cited_sources: list[str] = []
        transaction_count = input_summary.get("transaction_count")
        if transaction_count:
            cited_sources.append(f"账本：{transaction_count} 笔已加载交易")
        for tool_call in record.get("tool_calls") or []:
            if tool_call.get("name") == "query_transactions" and tool_call.get("status") == "called":
                cited_sources.append("类型化账本查询（参数化筛选）")
                break

        audit_status = record.get("audit_status")
        audit = EvidenceAudit(status=str(audit_status), warnings=[]) if audit_status else None

        tool_names = sorted(
            {
                str(tool_call.get("name"))
                for tool_call in record.get("tool_calls") or []
                if tool_call.get("status") == "called"
            }
        )

        return UserEvidenceProjection(
            request_id=request_id,
            findings=findings,
            cited_sources=cited_sources,
            data_coverage=DataCoverage(
                period=None,
                source_counts=source_counts,
                quality_warnings=quality_warnings,
            ),
            steps=project_steps(record),
            audit=audit,
            advanced=AdvancedDetails(run_id=request_id, tool_names=tool_names),
        )
    except Exception:
        logger.exception("Failed to project evidence request_id=%s", request_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to load evidence"})
