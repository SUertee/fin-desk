"""Provider-neutral embedding contracts for reviewed knowledge."""

from __future__ import annotations

import math
import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.knowledge.contracts import KnowledgeQuery, KnowledgeRetrievalResult

EmbeddingPurpose = Literal["document", "query"]
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def _validate_component(value: str) -> str:
    normalized = value.strip()
    if not _COMPONENT_RE.fullmatch(normalized):
        raise ValueError("embedding identity contains unsupported characters")
    return normalized


class EmbeddingProvider(Protocol):
    provider_id: str
    model_id: str
    dimension: int

    def embed(
        self,
        texts: list[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> list[list[float]]:
        """Embed a bounded batch for document indexing or query retrieval."""


class KnowledgeEmbeddingTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=8, max_length=180)
    content: str = Field(min_length=1, max_length=5000)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class KnowledgeEmbeddingTargetSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_chunks: int = Field(ge=0)
    pending: list[KnowledgeEmbeddingTarget]


class KnowledgeEmbeddingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=8, max_length=180)
    provider_id: str
    model_id: str
    dimension: int = Field(ge=1, le=4096)
    vector: list[float] = Field(min_length=1, max_length=4096)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("provider_id", "model_id")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        return _validate_component(value)

    @model_validator(mode="after")
    def validate_vector(self) -> "KnowledgeEmbeddingRecord":
        if len(self.vector) != self.dimension:
            raise ValueError("embedding record dimension does not match vector")
        if not all(math.isfinite(value) for value in self.vector):
            raise ValueError("embedding record must contain finite numbers")
        if not any(value != 0 for value in self.vector):
            raise ValueError("embedding record cannot be all zero")
        return self


class KnowledgeEmbeddingSyncResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    model_id: str
    total_chunks: int = Field(ge=0)
    embedded_chunks: int = Field(ge=0)
    skipped_chunks: int = Field(ge=0)


class KnowledgeEmbeddingStore(Protocol):
    def pending_targets(
        self,
        *,
        provider_id: str,
        model_id: str,
        dimension: int,
    ) -> KnowledgeEmbeddingTargetSet:
        """Return chunks whose stored embedding is absent or outdated."""

    def save_embeddings(self, records: list[KnowledgeEmbeddingRecord]) -> None:
        """Persist a validated batch atomically."""

    def retrieve(
        self,
        query: KnowledgeQuery,
        *,
        provider_id: str,
        model_id: str,
        dimension: int,
        query_vector: list[float],
        min_score: float,
    ) -> KnowledgeRetrievalResult:
        """Return filtered vector evidence for one provider model."""


def validate_provider(provider: EmbeddingProvider) -> tuple[str, str, int]:
    provider_id = _validate_component(provider.provider_id)
    model_id = _validate_component(provider.model_id)
    dimension = int(provider.dimension)
    if not 1 <= dimension <= 4096:
        raise ValueError("embedding dimension must be between 1 and 4096")
    return provider_id, model_id, dimension


def validate_embedding_batch(
    provider: EmbeddingProvider,
    texts: list[str],
    vectors: list[list[float]],
) -> list[list[float]]:
    _, _, dimension = validate_provider(provider)
    if len(vectors) != len(texts):
        raise ValueError("embedding provider returned the wrong batch size")
    validated: list[list[float]] = []
    for vector in vectors:
        normalized = [float(value) for value in vector]
        if len(normalized) != dimension:
            raise ValueError("embedding provider returned the wrong dimension")
        if not all(math.isfinite(value) for value in normalized):
            raise ValueError("embedding vector must contain finite numbers")
        if not any(value != 0 for value in normalized):
            raise ValueError("embedding vector cannot be all zero")
        validated.append(normalized)
    return validated
