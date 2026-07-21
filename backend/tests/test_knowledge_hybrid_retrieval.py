from contextlib import contextmanager
from datetime import date

import pytest

from app.connectors.postgres import knowledge_vector_store
from app.knowledge import (
    HybridKnowledgeRetriever,
    KnowledgeEmbeddingTarget,
    KnowledgeEmbeddingTargetSet,
    KnowledgeFilters,
    KnowledgeQuery,
    KnowledgeRetrievalResult,
    VectorKnowledgeRetriever,
    build_knowledge_evidence,
    sync_knowledge_embeddings,
)
from app.knowledge.embeddings import validate_embedding_batch
from app.knowledge.embeddings import KnowledgeEmbeddingRecord
from app.knowledge.markdown_ingestion import DEFAULT_CORPUS, parse_markdown_file


class FakeProvider:
    provider_id = "test-provider"
    model_id = "test-model-v1"
    dimension = 3

    def __init__(self):
        self.calls = []

    def embed(self, texts, *, purpose):
        self.calls.append((purpose, texts))
        return [[1.0, float(index + 1), 0.5] for index, _ in enumerate(texts)]


class FakeEmbeddingStore:
    def __init__(self, targets):
        self.targets = list(targets)
        self.saved = []

    def pending_targets(self, **_identity):
        return KnowledgeEmbeddingTargetSet(
            total_chunks=2,
            pending=list(self.targets),
        )

    def save_embeddings(self, records):
        self.saved.extend(records)
        saved_ids = {record.chunk_id for record in records}
        self.targets = [item for item in self.targets if item.chunk_id not in saved_ids]

    def retrieve(self, *_args, **_kwargs):
        raise AssertionError("sync test should not retrieve")


def _target(index: int):
    return KnowledgeEmbeddingTarget(
        chunk_id=f"document-section-{index}",
        content=f"section content {index}",
        content_hash=str(index) * 64,
    )


def _artifact(document_name: str, chunk_index: int = 0):
    bundle = parse_markdown_file(DEFAULT_CORPUS / document_name)
    return build_knowledge_evidence(
        bundle.document,
        bundle.chunks[chunk_index],
        retrieval_method="lexical",
        score=5.0,
        as_of=date(2026, 7, 21),
    )


@pytest.mark.parametrize(
    "vectors",
    [
        [[1.0, 2.0]],
        [[1.0, float("nan"), 2.0]],
        [[0.0, 0.0, 0.0]],
        [],
    ],
)
def test_embedding_validation_rejects_malformed_provider_output(vectors):
    with pytest.raises(ValueError):
        validate_embedding_batch(FakeProvider(), ["text"], vectors)


def test_embedding_record_cannot_bypass_dimension_validation():
    with pytest.raises(ValueError, match="dimension does not match"):
        KnowledgeEmbeddingRecord(
            chunk_id="document-section-1",
            provider_id="test-provider",
            model_id="test-model-v1",
            dimension=3,
            vector=[1.0, 2.0],
            content_hash="1" * 64,
        )


def test_embedding_sync_is_versioned_batched_and_idempotent():
    provider = FakeProvider()
    store = FakeEmbeddingStore([_target(1), _target(2)])

    first = sync_knowledge_embeddings(provider, store, batch_size=1)
    second = sync_knowledge_embeddings(provider, store, batch_size=1)

    assert first.embedded_chunks == 2
    assert first.skipped_chunks == 0
    assert second.embedded_chunks == 0
    assert second.skipped_chunks == 2
    assert [call[0] for call in provider.calls] == ["document", "document"]
    assert len(store.saved) == 2
    assert all(record.dimension == 3 for record in store.saved)


class FakeRetriever:
    def __init__(self, artifacts):
        self.artifacts = artifacts
        self.queries = []

    def retrieve(self, query):
        self.queries.append(query)
        return KnowledgeRetrievalResult(
            query=query.text,
            match_status="matched" if self.artifacts else "no_match",
            artifacts=self.artifacts,
        )


def test_hybrid_retrieval_deduplicates_and_fuses_rank_deterministically():
    shared = _artifact("au-emergency-fund.md")
    lexical_only = _artifact("au-budget-foundation.md")
    vector_only = _artifact("us-emergency-savings.md")
    lexical = FakeRetriever([shared, lexical_only])
    vector = FakeRetriever([shared.model_copy(update={"retrieval_method": "vector"}), vector_only])
    retriever = HybridKnowledgeRetriever(lexical, vector)

    first = retriever.retrieve(KnowledgeQuery(text="cash buffer", top_k=2))
    second = retriever.retrieve(KnowledgeQuery(text="cash buffer", top_k=2))

    assert first == second
    assert len(first.artifacts) == 2
    assert first.artifacts[0].chunk_id == shared.chunk_id
    assert first.artifacts[0].retrieval_method == "hybrid"
    assert len({item.chunk_id for item in first.artifacts}) == 2
    assert lexical.queries[0].top_k == 4
    assert vector.queries[0].top_k == 4


class FailingProvider(FakeProvider):
    def embed(self, texts, *, purpose):
        raise RuntimeError("provider unavailable")


def test_vector_retriever_does_not_hide_provider_failure():
    retriever = VectorKnowledgeRetriever(FailingProvider(), FakeEmbeddingStore([]))

    with pytest.raises(RuntimeError, match="provider unavailable"):
        retriever.retrieve(KnowledgeQuery(text="emergency fund"))


def _vector_row(score=0.91):
    bundle = parse_markdown_file(DEFAULT_CORPUS / "au-emergency-fund.md")
    document = bundle.document
    chunk = bundle.chunks[0]
    return (
        document.document_id,
        document.title,
        document.source_url,
        document.source_authority,
        document.source_type,
        document.jurisdiction,
        document.language,
        document.source_updated_at,
        document.reviewed_at,
        document.review_after,
        document.tags,
        document.content_hash,
        chunk.chunk_id,
        chunk.ordinal,
        chunk.heading,
        chunk.content,
        chunk.content_hash,
        score,
    )


class VectorCursor:
    def __init__(self, rows):
        self.rows = rows
        self.statement = ""
        self.params = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params):
        self.statement = statement
        self.params = params

    def fetchall(self):
        return self.rows


class VectorConnection:
    def __init__(self, rows):
        self.cursor_instance = VectorCursor(rows)

    def cursor(self):
        return self.cursor_instance


def test_pgvector_retrieval_applies_filters_and_projects_typed_evidence(monkeypatch):
    connection = VectorConnection([_vector_row()])

    @contextmanager
    def fake_conn():
        yield connection

    monkeypatch.setattr(knowledge_vector_store, "get_conn", fake_conn)
    store = knowledge_vector_store.PostgresKnowledgeEmbeddingStore()
    query = KnowledgeQuery(
        text="cash buffer",
        as_of=date(2026, 7, 21),
        filters=KnowledgeFilters(jurisdictions=["AU"], tags=["emergency fund"]),
    )

    result = store.retrieve(
        query,
        provider_id="test-provider",
        model_id="test-model-v1",
        dimension=3,
        query_vector=[1.0, 0.5, 0.25],
        min_score=0.3,
    )

    assert result.match_status == "matched"
    assert result.artifacts[0].retrieval_method == "vector"
    assert result.artifacts[0].document_id == "au-emergency-fund"
    assert "e.embedding <=> %s::vector" in connection.cursor_instance.statement
    assert "ANY(%s::text[])" in connection.cursor_instance.statement
    assert "cash buffer" not in connection.cursor_instance.statement
    assert connection.cursor_instance.params[-1] == 4


def test_schema_has_versioned_unbounded_vector_storage():
    schema = (
        knowledge_vector_store.__file__.replace("knowledge_vector_store.py", "schema.sql")
    )
    content = open(schema, encoding="utf-8").read()

    assert "CREATE TABLE IF NOT EXISTS knowledge_chunk_embeddings" in content
    assert "embedding     VECTOR NOT NULL" in content
    assert "PRIMARY KEY (chunk_id, provider_id, model_id)" in content
    assert "vector_dims(embedding) = dimension" in content
