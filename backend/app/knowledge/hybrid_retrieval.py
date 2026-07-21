"""Embedding synchronization and deterministic hybrid knowledge retrieval."""

from __future__ import annotations

from app.knowledge.contracts import (
    KnowledgeEvidenceArtifact,
    KnowledgeQuery,
    KnowledgeRetrievalResult,
    KnowledgeRetriever,
)
from app.knowledge.embeddings import (
    EmbeddingProvider,
    KnowledgeEmbeddingRecord,
    KnowledgeEmbeddingStore,
    KnowledgeEmbeddingSyncResult,
    validate_embedding_batch,
    validate_provider,
)


def sync_knowledge_embeddings(
    provider: EmbeddingProvider,
    store: KnowledgeEmbeddingStore,
    *,
    batch_size: int = 64,
) -> KnowledgeEmbeddingSyncResult:
    provider_id, model_id, dimension = validate_provider(provider)
    if not 1 <= batch_size <= 256:
        raise ValueError("batch_size must be between 1 and 256")
    target_set = store.pending_targets(
        provider_id=provider_id,
        model_id=model_id,
        dimension=dimension,
    )
    embedded_chunks = 0
    for offset in range(0, len(target_set.pending), batch_size):
        batch = target_set.pending[offset : offset + batch_size]
        texts = [target.content for target in batch]
        vectors = validate_embedding_batch(
            provider,
            texts,
            provider.embed(texts, purpose="document"),
        )
        store.save_embeddings(
            [
                KnowledgeEmbeddingRecord(
                    chunk_id=target.chunk_id,
                    provider_id=provider_id,
                    model_id=model_id,
                    dimension=dimension,
                    vector=vector,
                    content_hash=target.content_hash,
                )
                for target, vector in zip(batch, vectors, strict=True)
            ]
        )
        embedded_chunks += len(batch)
    return KnowledgeEmbeddingSyncResult(
        provider_id=provider_id,
        model_id=model_id,
        total_chunks=target_set.total_chunks,
        embedded_chunks=embedded_chunks,
        skipped_chunks=target_set.total_chunks - embedded_chunks,
    )


class VectorKnowledgeRetriever:
    def __init__(
        self,
        provider: EmbeddingProvider,
        store: KnowledgeEmbeddingStore,
        *,
        min_score: float = 0.25,
    ) -> None:
        self.provider = provider
        self.store = store
        self.provider_id, self.model_id, self.dimension = validate_provider(provider)
        if not 0 <= min_score <= 1:
            raise ValueError("min_score must be between 0 and 1")
        self.min_score = min_score

    def retrieve(self, query: KnowledgeQuery) -> KnowledgeRetrievalResult:
        vectors = validate_embedding_batch(
            self.provider,
            [query.text],
            self.provider.embed([query.text], purpose="query"),
        )
        return self.store.retrieve(
            query,
            provider_id=self.provider_id,
            model_id=self.model_id,
            dimension=self.dimension,
            query_vector=vectors[0],
            min_score=self.min_score,
        )


class HybridKnowledgeRetriever:
    def __init__(
        self,
        lexical: KnowledgeRetriever,
        vector: KnowledgeRetriever,
        *,
        rrf_k: int = 60,
    ) -> None:
        if not 1 <= rrf_k <= 1000:
            raise ValueError("rrf_k must be between 1 and 1000")
        self.lexical = lexical
        self.vector = vector
        self.rrf_k = rrf_k

    def retrieve(self, query: KnowledgeQuery) -> KnowledgeRetrievalResult:
        candidate_k = min(10, max(query.top_k, query.top_k * 2))
        candidate_query = query.model_copy(update={"top_k": candidate_k})
        sources = [
            self.lexical.retrieve(candidate_query),
            self.vector.retrieve(candidate_query),
        ]
        scores: dict[str, float] = {}
        artifacts: dict[str, KnowledgeEvidenceArtifact] = {}
        for source in sources:
            for rank, artifact in enumerate(source.artifacts, start=1):
                scores[artifact.chunk_id] = scores.get(artifact.chunk_id, 0.0) + (
                    1 / (self.rrf_k + rank)
                )
                artifacts.setdefault(artifact.chunk_id, artifact)

        ranked_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
        fused = [
            artifacts[chunk_id].model_copy(
                update={
                    "retrieval_method": "hybrid",
                    "score": round(scores[chunk_id], 8),
                }
            )
            for chunk_id in ranked_ids[: query.top_k]
        ]
        return KnowledgeRetrievalResult(
            query=query.text,
            match_status="matched" if fused else "no_match",
            artifacts=fused,
        )
