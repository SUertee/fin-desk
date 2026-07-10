"""Statement import endpoints."""

import logging

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.connectors.statement_sources import StatementImportError
from app.services.statement_import_service import (
    StatementPersistenceUnavailable,
    import_statement_file,
)

logger = logging.getLogger(__name__)
router = APIRouter()


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
