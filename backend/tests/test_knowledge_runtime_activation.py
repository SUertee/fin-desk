import pytest

from app.config.settings import KnowledgeSettings, get_settings
from app.connectors.embeddings import SiliconFlowEmbeddingProvider
from app.connectors.postgres.knowledge_store import (
    PostgresLexicalKnowledgeRetriever,
)
from app.knowledge import KnowledgeEmbeddingTarget, KnowledgeEmbeddingTargetSet
from app.knowledge.factory import (
    KnowledgeConfigurationError,
    build_embedding_provider,
    build_knowledge_retriever,
)
from app.knowledge.hybrid_retrieval import HybridKnowledgeRetriever
from app.knowledge.sync_embeddings import sync_configured_embeddings


def _settings(**updates):
    values = {
        "retrieval_mode": "lexical",
        "embedding_provider": "siliconflow",
        "allowed_embedding_providers": ("siliconflow",),
        "embedding_api_key": "",
        "embedding_model": "BAAI/bge-m3",
        "embedding_dimension": 3,
        "embedding_batch_size": 2,
    }
    values.update(updates)
    return KnowledgeSettings(**values)


def test_lexical_mode_has_no_embedding_dependency():
    retriever = build_knowledge_retriever(_settings())

    assert isinstance(retriever, PostgresLexicalKnowledgeRetriever)


def test_hybrid_mode_requires_configured_provider_instead_of_falling_back():
    with pytest.raises(KnowledgeConfigurationError, match="SILICONFLOW_API_KEY"):
        build_knowledge_retriever(_settings(retrieval_mode="hybrid"))


def test_hybrid_mode_builds_siliconflow_adapter_behind_existing_contract():
    settings = _settings(retrieval_mode="hybrid", embedding_api_key="test-key")

    retriever = build_knowledge_retriever(settings)

    assert isinstance(retriever, HybridKnowledgeRetriever)
    assert isinstance(retriever.vector.provider, SiliconFlowEmbeddingProvider)
    assert retriever.vector.provider.model_id == "BAAI/bge-m3"
    assert retriever.vector.provider.dimension == 3


def test_embedding_key_is_redacted_from_settings_repr():
    settings = _settings(embedding_api_key="private-key")

    assert "private-key" not in repr(settings)


class FakeProvider:
    provider_id = "test-provider"
    model_id = "test-model"
    dimension = 3

    def __init__(self):
        self.calls = []

    def embed(self, texts, *, purpose):
        self.calls.append((texts, purpose))
        return [[1.0, 0.5, 0.25] for _ in texts]


class FakeStore:
    def __init__(self):
        self.saved = []

    def pending_targets(self, **_identity):
        return KnowledgeEmbeddingTargetSet(
            total_chunks=1,
            pending=[
                KnowledgeEmbeddingTarget(
                    chunk_id="document-section-0",
                    content="reviewed guidance",
                    content_hash="a" * 64,
                )
            ],
        )

    def save_embeddings(self, records):
        self.saved.extend(records)


def test_sync_service_uses_configured_batch_and_existing_contract():
    provider = FakeProvider()
    store = FakeStore()

    result = sync_configured_embeddings(
        _settings(),
        provider=provider,
        store=store,
    )

    assert result.embedded_chunks == 1
    assert provider.calls == [(["reviewed guidance"], "document")]
    assert len(store.saved) == 1


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("retrieval_mode", "automatic", "mode"),
        ("embedding_batch_size", 0, "batch size"),
        ("embedding_dimension", 5000, "dimension"),
        ("vector_min_score", 1.1, "vector score"),
        ("embedding_base_url", "http://api.siliconflow.cn/v1", "HTTPS"),
    ],
)
def test_knowledge_settings_reject_invalid_bounds(field, value, expected):
    with pytest.raises(ValueError, match=expected):
        _settings(**{field: value})


def test_environment_maps_siliconflow_knowledge_settings(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_RETRIEVAL_MODE", "hybrid")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "runtime-key")
    monkeypatch.setenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("SILICONFLOW_EMBEDDING_DIMENSION", "1024")
    get_settings.cache_clear()
    try:
        settings = get_settings().knowledge
        assert settings.retrieval_mode == "hybrid"
        assert settings.embedding_api_key == "runtime-key"
        assert settings.embedding_model == "BAAI/bge-m3"
        assert settings.embedding_dimension == 1024
    finally:
        get_settings.cache_clear()
