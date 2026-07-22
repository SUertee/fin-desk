"""Composition root for lexical and hybrid reviewed-knowledge retrieval."""

from __future__ import annotations

from app.config.settings import KnowledgeSettings, get_settings
from app.connectors.embeddings import SiliconFlowEmbeddingProvider
from app.connectors.postgres.knowledge_store import (
    PostgresLexicalKnowledgeRetriever,
)
from app.connectors.postgres.knowledge_vector_store import (
    PostgresKnowledgeEmbeddingStore,
)
from app.knowledge.contracts import KnowledgeRetriever
from app.knowledge.embeddings import EmbeddingProvider
from app.knowledge.hybrid_retrieval import (
    HybridKnowledgeRetriever,
    VectorKnowledgeRetriever,
)


class KnowledgeConfigurationError(ValueError):
    pass


def build_embedding_provider(settings: KnowledgeSettings) -> EmbeddingProvider:
    if settings.embedding_provider != "siliconflow":
        raise KnowledgeConfigurationError(
            f"unsupported knowledge embedding provider: {settings.embedding_provider}"
        )
    if not settings.embedding_api_key:
        raise KnowledgeConfigurationError(
            "SILICONFLOW_API_KEY is required for knowledge embeddings"
        )
    return SiliconFlowEmbeddingProvider(
        api_key=settings.embedding_api_key,
        model_id=settings.embedding_model,
        dimension=settings.embedding_dimension,
        base_url=settings.embedding_base_url,
        timeout_seconds=settings.embedding_timeout_seconds,
        max_batch_size=settings.embedding_batch_size,
    )


def build_knowledge_retriever(
    settings: KnowledgeSettings | None = None,
) -> KnowledgeRetriever:
    configured = settings or get_settings().knowledge
    lexical = PostgresLexicalKnowledgeRetriever()
    if configured.retrieval_mode == "lexical":
        return lexical

    provider = build_embedding_provider(configured)
    vector = VectorKnowledgeRetriever(
        provider,
        PostgresKnowledgeEmbeddingStore(),
        min_score=configured.vector_min_score,
    )
    return HybridKnowledgeRetriever(lexical, vector, rrf_k=configured.rrf_k)
