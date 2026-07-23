"""Polling worker for watched-folder and read-only email statement intake."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from app.config.settings import get_settings
from app.connectors.postgres.connection import close_pool, init_pool
from app.connectors.postgres.statement_import_store import (
    get_statement_import_settings_db,
    list_statement_import_settings_db,
)
from app.connectors.statement_intake import StatementCandidate
from app.connectors.statement_intake.email import StatementEmailConnector
from app.connectors.statement_intake.folder import StatementFolderScanner
from app.services.statement_import_service import StatementPersistenceUnavailable
from app.services.statement_ingestion import ingest_statement_candidate

logger = logging.getLogger(__name__)


def scan_folder_once(user_settings: dict[str, Any]) -> list[dict[str, Any]]:
    settings = get_settings().statement_ingestion
    if not user_settings.get("folder_enabled"):
        return []
    scanner = StatementFolderScanner(
        settings.inbox_path,
        stable_seconds=settings.stable_seconds,
        max_file_bytes=settings.max_file_bytes,
    )
    outcomes: list[dict[str, Any]] = []
    for path in scanner.scan(str(user_settings.get("folder_subdirectory") or "")):
        try:
            outcome = ingest_statement_candidate(
                StatementCandidate(
                    user_id=user_settings["user_id"],
                    filename=path.name,
                    content=path.read_bytes(),
                    channel="folder",
                    origin_key=str(path),
                    origin_metadata={"watched_path": str(path)},
                ),
                auto_commit=bool(user_settings.get("auto_commit", True)),
            )
            outcomes.append(outcome)
            path.unlink(missing_ok=True)
        except StatementPersistenceUnavailable:
            logger.exception("Statement persistence unavailable path=%s", path)
        except Exception:
            logger.exception("Failed to ingest watched statement path=%s", path)
            path.unlink(missing_ok=True)
    return outcomes


def scan_email_once(user_settings: dict[str, Any]) -> list[dict[str, Any]]:
    settings = get_settings().statement_ingestion
    if not user_settings.get("email_enabled") or not settings.email_available:
        return []
    connector = StatementEmailConnector(settings)
    outcomes: list[dict[str, Any]] = []
    for candidate in connector.fetch_candidates(
        user_id=user_settings["user_id"],
        mailbox=str(user_settings.get("email_mailbox") or "INBOX"),
        allowed_senders=list(user_settings.get("email_allowed_senders") or []),
    ):
        outcomes.append(
            ingest_statement_candidate(
                candidate,
                auto_commit=bool(user_settings.get("auto_commit", True)),
            )
        )
    return outcomes


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    init_pool()
    app_settings = get_settings()
    ingestion = app_settings.statement_ingestion
    last_email_scan = 0.0
    try:
        while True:
            user_settings = list_statement_import_settings_db()
            if not user_settings:
                user_settings = [
                    get_statement_import_settings_db(app_settings.default_user_id)
                ]
            for item in user_settings:
                scan_folder_once(item)
            now = time.monotonic()
            if now - last_email_scan >= ingestion.email_poll_seconds:
                for item in user_settings:
                    try:
                        scan_email_once(item)
                    except Exception:
                        logger.exception(
                            "Failed to poll statement email user=%s",
                            item["user_id"],
                        )
                last_email_scan = now
            time.sleep(ingestion.poll_seconds)
    except KeyboardInterrupt:
        logger.info("Statement inbox worker stopped")
    finally:
        close_pool()


if __name__ == "__main__":
    run()
