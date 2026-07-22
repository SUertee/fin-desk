"""Explicit maintenance command for reviewed-knowledge embeddings."""

from __future__ import annotations

import sys

from app.config.settings import KnowledgeSettings, get_settings
from app.connectors.postgres.connection import close_pool, init_pool
from app.connectors.postgres.knowledge_vector_store import (
    PostgresKnowledgeEmbeddingStore,
)
from app.knowledge.embeddings import (
    EmbeddingProvider,
    KnowledgeEmbeddingStore,
    KnowledgeEmbeddingSyncResult,
)
from app.knowledge.factory import (
    KnowledgeConfigurationError,
    build_embedding_provider,
)
from app.knowledge.hybrid_retrieval import sync_knowledge_embeddings


def sync_configured_embeddings(
    settings: KnowledgeSettings,
    *,
    provider: EmbeddingProvider | None = None,
    store: KnowledgeEmbeddingStore | None = None,
) -> KnowledgeEmbeddingSyncResult:
    return sync_knowledge_embeddings(
        provider or build_embedding_provider(settings),
        store or PostgresKnowledgeEmbeddingStore(),
        batch_size=settings.embedding_batch_size,
    )


def _main() -> int:
    from dotenv import load_dotenv

    load_dotenv()
    get_settings.cache_clear()
    settings = get_settings().knowledge
    try:
        provider = build_embedding_provider(settings)
    except KnowledgeConfigurationError as exc:
        print(f"knowledge embedding configuration error: {exc}", file=sys.stderr)
        return 2
    init_pool()
    try:
        result = sync_configured_embeddings(settings, provider=provider)
    finally:
        close_pool()
    print(
        f"knowledge embeddings: {result.embedded_chunks} embedded, "
        f"{result.skipped_chunks} skipped, {result.total_chunks} total "
        f"({result.provider_id}/{result.model_id})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
