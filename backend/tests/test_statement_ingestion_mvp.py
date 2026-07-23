from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace

from app.config.settings import StatementIngestionSettings
from app.connectors.statement_intake import StatementCandidate
from app.connectors.statement_intake.email import StatementEmailConnector
from app.connectors.statement_intake.folder import StatementFolderScanner
from app.connectors.statement_intake.storage import StatementFileStore
from app.connectors.statement_sources.contracts import ParseReport
from app.connectors.statement_sources import StatementImportError
from app.services import statement_ingestion
from app.services.statement_import_service import (
    PreparedStatementImport,
    StatementImportResult,
)
from app.services.statement_quality_gate import evaluate_statement_quality


def _prepared(*, reconciliation: str, rows: int = 1, already: int = 0):
    report = ParseReport(detected_source="alipay", encoding_or_format="gb18030")
    quality = {
        "reconciliation": {"status": reconciliation, "checks": []},
        "skipped_by_reason": {},
    }
    return PreparedStatementImport(
        user_id="demo",
        source_file="bill.csv",
        report=report,
        rows=[{"date": "2026-06-01", "amount": -10}] * rows,
        duplicates=[],
        already_imported_count=already,
        quality_report=quality,
    )


def test_quality_gate_auto_commits_only_reconciled_rows():
    assert evaluate_statement_quality(
        _prepared(reconciliation="matched"), auto_commit=True
    ).action == "auto_commit"
    decision = evaluate_statement_quality(
        _prepared(reconciliation="not_available"), auto_commit=True
    )
    assert decision.action == "review_required"
    assert decision.reasons == ["reconciliation_not_available"]


def test_quality_gate_recognizes_complete_reimport():
    decision = evaluate_statement_quality(
        _prepared(reconciliation="matched", rows=0, already=4), auto_commit=True
    )
    assert decision.action == "duplicate"


def test_folder_scanner_is_shallow_stable_and_bounded(tmp_path: Path):
    ready = tmp_path / "ready.csv"
    ready.write_text("date,amount\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.csv").write_text("ignored", encoding="utf-8")
    (tmp_path / "note.txt").write_text("ignored", encoding="utf-8")

    scanner = StatementFolderScanner(
        tmp_path,
        stable_seconds=0,
        max_file_bytes=100,
    )
    assert scanner.scan() == [ready]


def test_private_store_moves_review_file(tmp_path: Path):
    store = StatementFileStore(tmp_path)
    processing = store.save("imp_1", "bill.csv", b"content")
    review = store.move(processing, "review")
    assert review.read_bytes() == b"content"
    assert review.parent.name == "review"
    assert store.reference(review).startswith("review/")
    assert store.read(store.reference(review)) == b"content"


def test_review_candidate_never_commits_transactions(monkeypatch, tmp_path: Path):
    prepared = _prepared(reconciliation="mismatch")
    saved_records = []
    committed = []
    monkeypatch.setattr(
        statement_ingestion,
        "get_settings",
        lambda: SimpleNamespace(
            statement_ingestion=SimpleNamespace(
                max_file_bytes=1_000,
                storage_path=tmp_path,
            )
        ),
    )
    monkeypatch.setattr(
        statement_ingestion, "get_statement_import_by_hash_db", lambda *_: None
    )
    monkeypatch.setattr(
        statement_ingestion,
        "prepare_statement_file",
        lambda **_: prepared,
    )

    def save(**kwargs):
        saved_records.append(kwargs)
        return {**kwargs, "created_at": "now", "updated_at": "now"}

    monkeypatch.setattr(statement_ingestion, "save_statement_import_record_db", save)
    monkeypatch.setattr(
        statement_ingestion,
        "commit_prepared_statement",
        lambda *_args, **_kwargs: committed.append(True),
    )

    result = statement_ingestion.ingest_statement_candidate(
        StatementCandidate(
            user_id="demo",
            filename="bill.csv",
            content=b"statement",
            channel="folder",
        ),
        auto_commit=True,
    )

    assert result["record"]["status"] == "review_required"
    assert not committed
    assert Path(result["record"]["stored_path"]).parent.name == "review"


def test_reconciled_candidate_commits_once(monkeypatch, tmp_path: Path):
    prepared = _prepared(reconciliation="matched")
    committed = []
    monkeypatch.setattr(
        statement_ingestion,
        "get_settings",
        lambda: SimpleNamespace(
            statement_ingestion=SimpleNamespace(
                max_file_bytes=1_000,
                storage_path=tmp_path,
            )
        ),
    )
    monkeypatch.setattr(
        statement_ingestion, "get_statement_import_by_hash_db", lambda *_: None
    )
    monkeypatch.setattr(
        statement_ingestion, "prepare_statement_file", lambda **_: prepared
    )
    monkeypatch.setattr(
        statement_ingestion,
        "save_statement_import_record_db",
        lambda **kwargs: {**kwargs, "created_at": "now", "updated_at": "now"},
    )

    def commit(value, *, persist_import_record):
        committed.append((value, persist_import_record))
        return StatementImportResult(
            ok=True,
            user_id="demo",
            source_file="bill.csv",
            imported_count=1,
        )

    monkeypatch.setattr(statement_ingestion, "commit_prepared_statement", commit)
    result = statement_ingestion.ingest_statement_candidate(
        StatementCandidate(
            user_id="demo",
            filename="bill.csv",
            content=b"statement",
            channel="upload",
        ),
        auto_commit=True,
    )

    assert len(committed) == 1
    assert committed[0][1] is False
    assert result["record"]["status"] == "succeeded"
    assert "archive" in Path(result["record"]["stored_path"]).parts


def test_unrecognized_statement_is_held_for_review(monkeypatch, tmp_path: Path):
    committed = []
    monkeypatch.setattr(
        statement_ingestion,
        "get_settings",
        lambda: SimpleNamespace(
            statement_ingestion=SimpleNamespace(
                max_file_bytes=1_000,
                storage_path=tmp_path,
            )
        ),
    )
    monkeypatch.setattr(
        statement_ingestion, "get_statement_import_by_hash_db", lambda *_: None
    )
    monkeypatch.setattr(
        statement_ingestion,
        "prepare_statement_file",
        lambda **_: (_ for _ in ()).throw(StatementImportError("unknown layout")),
    )
    monkeypatch.setattr(
        statement_ingestion,
        "save_statement_import_record_db",
        lambda **kwargs: {**kwargs, "created_at": "now", "updated_at": "now"},
    )
    monkeypatch.setattr(
        statement_ingestion,
        "commit_prepared_statement",
        lambda *_args, **_kwargs: committed.append(True),
    )

    result = statement_ingestion.ingest_statement_candidate(
        StatementCandidate(
            user_id="demo",
            filename="unknown.csv",
            content=b"unknown-layout",
            channel="folder",
        ),
        auto_commit=True,
    )

    assert result["record"]["status"] == "review_required"
    assert result["record"]["error"] == "unknown layout"
    assert result["record"]["quality_report"]["gate"]["reasons"] == [
        "unrecognized_or_unparseable_statement"
    ]
    assert not committed
    assert Path(result["record"]["stored_path"]).parent.name == "review"


def test_email_connector_reads_allowed_attachments_without_marking_seen(monkeypatch):
    message = EmailMessage()
    message["From"] = "Billing <billing@example.com>"
    message["Subject"] = "Monthly statement"
    message["Message-ID"] = "<statement-1@example.com>"
    message.set_content("Statement attached")
    message.add_attachment(
        b"date,amount\n2026-06-01,-10\n",
        maintype="text",
        subtype="csv",
        filename="bill.csv",
    )

    class FakeClient:
        def __init__(self):
            self.selected = None
            self.fetch_query = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def select(self, mailbox, readonly=False):
            self.selected = (mailbox, readonly)
            return "OK", []

        def uid(self, command, *_args):
            if command == "search":
                return "OK", [b"42"]
            self.fetch_query = _args[-1]
            return "OK", [(b"42", message.as_bytes())]

    client = FakeClient()
    connector = StatementEmailConnector(
        StatementIngestionSettings(
            email_host="imap.example.com",
            email_username="user",
            email_password="secret",
        )
    )
    monkeypatch.setattr(connector, "_client", lambda: client)

    candidates = connector.fetch_candidates(
        user_id="demo",
        mailbox="Statements",
        allowed_senders=["billing@example.com"],
    )

    assert client.selected == ("Statements", True)
    assert client.fetch_query == "(BODY.PEEK[])"
    assert len(candidates) == 1
    assert candidates[0].filename == "bill.csv"
    assert candidates[0].origin_metadata["sender"] == "billing@example.com"
