"""HTTP routes for user-uploaded documents.

MVEP exposes upload (sync), list, and delete. ``source_kind=chat_attachment``
is the same pipeline as a knowledge-library upload; the chat surface adds it
to the current conversation context separately (P5). Ingestion runs inline
today; P3 moves the heavy work to the async worker.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.connectors.document_intake import DocumentCandidate
from app.connectors.document_sources import UnsupportedDocumentType
from app.connectors.postgres.user_document_store import UserDocumentStore
from app.services.document_ingestion import build_document_ingestion_service

router = APIRouter(prefix="/knowledge-documents", tags=["knowledge-documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    source_kind: str = Form("upload"),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty upload")
    candidate = DocumentCandidate(
        user_id=user_id,
        filename=file.filename or "upload",
        content=content,
        mime_type=file.content_type or "application/octet-stream",
        source_kind=(
            source_kind if source_kind in ("upload", "chat_attachment") else "upload"
        ),
    )
    service = build_document_ingestion_service()
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "document ingestion is not configured "
                "(OBJECT_STORAGE_ACCESS_KEY/SECRET_KEY or SILICONFLOW_API_KEY missing)"
            ),
        )
    try:
        result = service.ingest(candidate)
    except UnsupportedDocumentType as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    return {
        "document_id": result.document_id,
        "status": result.status,
        "chunk_count": result.chunk_count,
        "image_count": result.image_count,
        "error": result.error,
    }


@router.get("")
def list_documents():
    return {"documents": UserDocumentStore().list_documents()}


@router.delete("/{document_id}")
def delete_document(document_id: int):
    deleted = UserDocumentStore().delete_document(document_id=document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="document not found")
    return {"deleted": True, "document_id": document_id}
