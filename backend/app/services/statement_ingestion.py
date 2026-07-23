"""Unified statement intake, quality-gate, review, and commit workflow."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config.settings import get_settings
from app.connectors.postgres.statement_import_store import (
    get_statement_import_by_hash_db,
    get_statement_import_record_db,
    save_statement_import_record_db,
)
from app.connectors.statement_intake import StatementCandidate
from app.connectors.statement_intake.storage import StatementFileStore
from app.connectors.statement_sources import StatementImportError
from app.services.statement_import_service import (
    StatementPersistenceUnavailable,
    commit_prepared_statement,
    prepare_statement_file,
)
from app.services.statement_quality_gate import evaluate_statement_quality


logger = logging.getLogger(__name__)


def ingest_statement_candidate(
    candidate: StatementCandidate,
    *,
    auto_commit: bool,
) -> dict[str, Any]:
    settings = get_settings().statement_ingestion
    if len(candidate.content) > settings.max_file_bytes:
        raise StatementImportError("Statement file exceeds the configured size limit.")

    content_hash = hashlib.sha256(candidate.content).hexdigest()
    existing = get_statement_import_by_hash_db(candidate.user_id, content_hash)
    if existing:
        return {"ok": True, "duplicate": True, "record": existing}

    import_id = f"imp_{uuid4().hex}"
    file_store = StatementFileStore(settings.storage_path)
    processing_path = file_store.save(import_id, candidate.filename, candidate.content)
    current_path = processing_path
    transactions_committed = False
    base_record = {
        "import_id": import_id,
        "user_id": candidate.user_id,
        "source_file": candidate.filename,
        "source_format": Path(candidate.filename).suffix.lower().lstrip("."),
        "ingestion_channel": candidate.channel,
        "content_hash": content_hash,
        "stored_path": file_store.reference(processing_path),
        "origin_key": candidate.origin_key,
        "origin_metadata": candidate.origin_metadata,
    }
    try:
        _save_required(status="processing", **base_record)
    except StatementPersistenceUnavailable:
        processing_path.unlink(missing_ok=True)
        raise

    try:
        prepared = prepare_statement_file(
            user_id=candidate.user_id,
            filename=candidate.filename,
            content=candidate.content,
        )
        decision = evaluate_statement_quality(prepared, auto_commit=auto_commit)
        quality_report = {
            **prepared.quality_report,
            "gate": {"action": decision.action, "reasons": decision.reasons},
        }
        common = {
            **base_record,
            "detected_source": prepared.report.detected_source,
            "sample": prepared.rows[:3],
            "quality_report": quality_report,
        }

        if decision.action == "review_required":
            review_path = file_store.move(processing_path, "review")
            current_path = review_path
            record = _save_required(
                status="review_required",
                stored_path=file_store.reference(review_path),
                **{key: value for key, value in common.items() if key != "stored_path"},
            )
            return {"ok": True, "duplicate": False, "record": record}

        if decision.action == "duplicate":
            archive_path = file_store.move(processing_path, "archive")
            current_path = archive_path
            record = _save_required(
                status="duplicate",
                stored_path=file_store.reference(archive_path),
                **{key: value for key, value in common.items() if key != "stored_path"},
            )
            return {"ok": True, "duplicate": True, "record": record}

        result = commit_prepared_statement(prepared, persist_import_record=False)
        transactions_committed = True
        archive_path = file_store.move(processing_path, "archive")
        current_path = archive_path
        record = _save_required(
            status="succeeded",
            imported_count=result.imported_count,
            stored_path=file_store.reference(archive_path),
            **{key: value for key, value in common.items() if key != "stored_path"},
        )
        return {
            **result.model_dump(),
            "duplicate": False,
            "import_record": record,
            "record": record,
        }
    except StatementImportError as exc:
        review_path = file_store.move(current_path, "review")
        record = _save_required(
            status="review_required",
            error=str(exc),
            quality_report={
                "gate": {
                    "action": "review_required",
                    "reasons": ["unrecognized_or_unparseable_statement"],
                }
            },
            stored_path=file_store.reference(review_path),
            **{key: value for key, value in base_record.items() if key != "stored_path"},
        )
        return {"ok": True, "duplicate": False, "record": record}
    except Exception as exc:
        failure_path = current_path
        if not transactions_committed and current_path.exists():
            try:
                failure_path = file_store.move(current_path, "rejected")
            except Exception:
                logger.exception("Failed to quarantine statement import=%s", import_id)
        save_statement_import_record_db(
            status="failed",
            error=str(exc),
            stored_path=file_store.reference(failure_path),
            **{key: value for key, value in base_record.items() if key != "stored_path"},
        )
        raise


def approve_statement_import(*, import_id: str, user_id: str) -> dict[str, Any]:
    record = _owned_review_record(import_id, user_id)
    file_store = StatementFileStore(get_settings().statement_ingestion.storage_path)
    content = file_store.read(record["stored_path"])
    prepared = prepare_statement_file(
        user_id=user_id,
        filename=record["source_file"],
        content=content,
    )
    result = commit_prepared_statement(prepared, persist_import_record=False)
    archive_path = file_store.move(record["stored_path"], "archive")
    updated = _save_required(
        import_id=import_id,
        user_id=user_id,
        source_file=record["source_file"],
        source_format=record["source_format"],
        detected_source=prepared.report.detected_source,
        imported_count=result.imported_count,
        status="succeeded",
        sample=result.sample,
        quality_report={
            **prepared.quality_report,
            "gate": {"action": "approved", "reasons": ["user_approved"]},
        },
        ingestion_channel=record["ingestion_channel"],
        content_hash=record["content_hash"],
        stored_path=file_store.reference(archive_path),
        origin_key=record["origin_key"],
        origin_metadata=record["origin_metadata"],
    )
    return {**result.model_dump(), "record": updated, "import_record": updated}


def reject_statement_import(*, import_id: str, user_id: str) -> dict[str, Any]:
    record = _owned_review_record(import_id, user_id)
    file_store = StatementFileStore(get_settings().statement_ingestion.storage_path)
    rejected_path = file_store.move(record["stored_path"], "rejected")
    updated = _save_required(
        **{
            key: record[key]
            for key in (
                "import_id", "user_id", "source_file", "source_format",
                "imported_count", "sample", "quality_report",
                "ingestion_channel", "content_hash", "detected_source",
                "origin_key", "origin_metadata",
            )
        },
        status="rejected",
        error="Rejected by user",
        stored_path=file_store.reference(rejected_path),
    )
    return {"ok": True, "record": updated}


def _owned_review_record(import_id: str, user_id: str) -> dict[str, Any]:
    record = get_statement_import_record_db(import_id)
    if not record or record["user_id"] != user_id:
        raise LookupError("Statement import not found")
    if record["status"] != "review_required":
        raise ValueError("Statement import is not awaiting review")
    return record


def _save_required(**record: Any) -> dict[str, Any]:
    saved = save_statement_import_record_db(**record)
    if not saved:
        raise StatementPersistenceUnavailable(
            "Statement metadata persistence is not available."
        )
    return saved
