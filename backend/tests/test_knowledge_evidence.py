from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

from app.connectors.postgres import knowledge_store
from app.knowledge.contracts import (
    KnowledgeIngestionResult,
    build_knowledge_evidence,
)
from app.knowledge.markdown_ingestion import (
    DEFAULT_CORPUS,
    ingest_paths,
    parse_markdown_document,
    parse_markdown_file,
)


def _sample_markdown(body: str = "# Rule\n\nKeep a cash buffer.") -> str:
    return f"""---
id: test-policy
title: Test policy
source_url: https://example.gov/policy
source_authority: Example Authority
source_type: official_guidance
jurisdiction: TEST
language: en
source_updated_at: 2026-07-01
reviewed_at: 2026-07-21
review_after: 2027-01-21
tags: savings, cash buffer
---
{body}
"""


def test_markdown_ingestion_is_deterministic_and_heading_aware():
    text = _sample_markdown("# First\n\nOne.\n\n# Second\n\nTwo.")

    first = parse_markdown_document(text)
    second = parse_markdown_document(text)

    assert first == second
    assert [chunk.heading for chunk in first.chunks] == ["First", "Second"]
    assert [chunk.ordinal for chunk in first.chunks] == [0, 1]
    assert first.document.tags == ["savings", "cash buffer"]


def test_markdown_requires_reviewed_provenance():
    with pytest.raises(ValueError, match="front matter"):
        parse_markdown_document("# Missing metadata")

    invalid = _sample_markdown().replace("review_after: 2027-01-21\n", "")
    with pytest.raises(ValueError, match="review_after"):
        parse_markdown_document(invalid)


def test_evidence_projection_is_bounded_and_marks_stale_policy():
    bundle = parse_markdown_document(_sample_markdown("# Rule\n\n" + "x" * 1500))
    chunk = bundle.chunks[0]

    current = build_knowledge_evidence(
        bundle.document,
        chunk,
        retrieval_method="lexical",
        score=0.8,
        as_of=date(2026, 8, 1),
    )
    stale = build_knowledge_evidence(
        bundle.document,
        chunk,
        retrieval_method="lexical",
        score=0.8,
        as_of=date(2027, 2, 1),
    )

    assert current.freshness == "current"
    assert stale.freshness == "stale"
    assert len(current.excerpt) == 1200
    assert current.source_url == "https://example.gov/policy"


def test_reviewed_corpus_parses_and_uses_official_sources():
    paths = sorted(DEFAULT_CORPUS.glob("*.md"))
    bundles = [parse_markdown_file(path) for path in paths]

    assert len(bundles) == 6
    assert len({bundle.document.document_id for bundle in bundles}) == 6
    assert all(bundle.document.source_type == "official_guidance" for bundle in bundles)
    assert all(
        bundle.document.source_url.startswith(
            ("https://moneysmart.gov.au/", "https://www.consumerfinance.gov/", "https://www.investor.gov/")
        )
        for bundle in bundles
    )
    assert all(bundle.document.freshness(as_of=date(2026, 7, 21)) == "current" for bundle in bundles)


def test_ingest_paths_requires_explicit_saver(tmp_path: Path):
    path = tmp_path / "policy.md"
    path.write_text(_sample_markdown(), encoding="utf-8")
    saved = []

    def saver(bundle):
        saved.append(bundle)
        return KnowledgeIngestionResult(
            document_id=bundle.document.document_id,
            status="created",
            chunk_count=len(bundle.chunks),
        )

    results = ingest_paths([tmp_path], saver=saver)

    assert [result.status for result in results] == ["created"]
    assert saved[0].document.document_id == "test-policy"


class FakeCursor:
    def __init__(self, existing_hash=None):
        self.existing_hash = existing_hash
        self.statements = []
        self.inserted_chunks = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))

    def executemany(self, statement, params):
        self.statements.append((statement, None))
        self.inserted_chunks.extend(params)

    def fetchone(self):
        return (self.existing_hash,) if self.existing_hash else None


class FakeConnection:
    def __init__(self, existing_hash=None):
        self.cursor_instance = FakeCursor(existing_hash)
        self.commits = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1


def test_knowledge_store_skips_unchanged_document(monkeypatch):
    bundle = parse_markdown_document(_sample_markdown())
    connection = FakeConnection(bundle.document.content_hash)

    @contextmanager
    def fake_conn():
        yield connection

    monkeypatch.setattr(knowledge_store, "get_conn", fake_conn)

    result = knowledge_store.save_knowledge_bundle_db(bundle)

    assert result.status == "unchanged"
    assert connection.commits == 0
    assert len(connection.cursor_instance.statements) == 1


def test_knowledge_store_replaces_changed_chunks_atomically(monkeypatch):
    bundle = parse_markdown_document(_sample_markdown())
    connection = FakeConnection("0" * 64)

    @contextmanager
    def fake_conn():
        yield connection

    monkeypatch.setattr(knowledge_store, "get_conn", fake_conn)

    result = knowledge_store.save_knowledge_bundle_db(bundle)

    assert result.status == "updated"
    assert connection.commits == 1
    assert len(connection.cursor_instance.inserted_chunks) == len(bundle.chunks)
