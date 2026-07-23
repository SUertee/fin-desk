"""Statement import endpoints."""

import logging

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse

from app.connectors.statement_sources import StatementImportError
from app.config.settings import get_settings
from app.connectors.postgres.statement_import_store import (
    get_statement_import_record_db,
    get_statement_import_settings_db,
    list_statement_import_records_db,
    save_statement_import_settings_db,
)
from app.connectors.statement_intake import StatementCandidate
from app.connectors.statement_intake.email import StatementEmailConnector
from app.models.statement_import import StatementImportSettingsUpdate
from app.services.statement_import_service import (
    StatementPersistenceUnavailable,
    import_statement_file,
)
from app.services.statement_ingestion import (
    approve_statement_import,
    ingest_statement_candidate,
    reject_statement_import,
)
from app.workers.statement_inbox import scan_folder_once

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/statement-imports/upload")
async def upload_statement_candidate(
    file: UploadFile = File(...),
    user_id: str = Form("demo"),
):
    try:
        user_settings = get_statement_import_settings_db(user_id)
        return ingest_statement_candidate(
            StatementCandidate(
                user_id=user_id,
                filename=file.filename or "statement.csv",
                content=await file.read(),
                channel="upload",
            ),
            auto_commit=bool(user_settings.get("auto_commit", True)),
        )
    except StatementImportError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
    except StatementPersistenceUnavailable as exc:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(exc)})
    except Exception:
        logger.exception("Failed to ingest statement for user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to ingest statement"})


@router.post("/statement-imports/scan")
def scan_statement_inbox(user_id: str = "demo"):
    return {"ok": True, "items": scan_folder_once(get_statement_import_settings_db(user_id))}


@router.get("/statement-imports")
def list_statement_imports(
    user_id: str = "demo",
    status: str | None = None,
    limit: int = Query(30, ge=1, le=100),
):
    return {
        "ok": True,
        "items": list_statement_import_records_db(user_id, limit=limit, status=status),
    }


@router.get("/statement-imports/settings/{user_id}")
def get_statement_settings(user_id: str):
    settings = get_statement_import_settings_db(user_id)
    runtime = get_settings().statement_ingestion
    return {
        "ok": True,
        "settings": settings,
        "runtime": {
            "inbox_path": str(runtime.inbox_path),
            "poll_seconds": runtime.poll_seconds,
            "stable_seconds": runtime.stable_seconds,
            "email_available": runtime.email_available,
        },
    }


@router.put("/statement-imports/settings/{user_id}")
def update_statement_settings(user_id: str, payload: StatementImportSettingsUpdate):
    saved = save_statement_import_settings_db(user_id, payload.model_dump())
    if not saved:
        return JSONResponse(status_code=503, content={"ok": False, "error": "Settings persistence is not available"})
    return {"ok": True, "settings": saved}


@router.post("/statement-imports/email/test")
def test_statement_email(user_id: str = "demo"):
    user_settings = get_statement_import_settings_db(user_id)
    try:
        result = StatementEmailConnector(
            get_settings().statement_ingestion
        ).test_connection(str(user_settings.get("email_mailbox") or "INBOX"))
        return result
    except Exception as exc:
        return JSONResponse(status_code=409, content={"ok": False, "error": str(exc)})


@router.get("/statement-imports/{import_id}")
def get_statement_import(import_id: str, user_id: str = "demo"):
    record = get_statement_import_record_db(import_id)
    if not record or record["user_id"] != user_id:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Statement import not found"})
    return {"ok": True, "record": record}


@router.post("/statement-imports/{import_id}/approve")
def approve_statement(import_id: str, user_id: str = "demo"):
    try:
        return approve_statement_import(import_id=import_id, user_id=user_id)
    except LookupError as exc:
        return JSONResponse(status_code=404, content={"ok": False, "error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=409, content={"ok": False, "error": str(exc)})


@router.post("/statement-imports/{import_id}/reject")
def reject_statement(import_id: str, user_id: str = "demo"):
    try:
        return reject_statement_import(import_id=import_id, user_id=user_id)
    except LookupError as exc:
        return JSONResponse(status_code=404, content={"ok": False, "error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=409, content={"ok": False, "error": str(exc)})


@router.post("/statement-import/import")
async def import_statement(
    file: UploadFile = File(...),
    user_id: str = Form("demo"),
):
    try:
        result = import_statement_file(
            user_id=user_id,
            filename=file.filename or "statement.csv",
            content=await file.read(),
        )
        return result.model_dump()
    except StatementImportError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
    except StatementPersistenceUnavailable as exc:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(exc)})
    except Exception:
        logger.exception("Failed to import statement for user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to import statement"})
