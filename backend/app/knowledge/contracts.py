"""Provider-neutral contracts for durable reviewed knowledge."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

KnowledgeSourceType = Literal[
    "official_guidance",
    "internal_policy",
    "user_document",
]
KnowledgeFreshness = Literal["current", "stale"]
KnowledgeRetrievalMethod = Literal["lexical", "vector", "hybrid"]
KnowledgeIngestionStatus = Literal["created", "updated", "unchanged"]

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_id(value: str) -> str:
    normalized = value.strip().lower()
    if not _ID_RE.fullmatch(normalized):
        raise ValueError("knowledge id must be a lowercase stable slug")
    return normalized


def _validate_hash(value: str) -> str:
    normalized = value.strip().lower()
    if not _HASH_RE.fullmatch(normalized):
        raise ValueError("content hash must be SHA-256 hex")
    return normalized


def _validate_http_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source URL must be absolute HTTP(S)")
    return normalized


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str = Field(min_length=1, max_length=240)
    source_url: str = Field(min_length=8, max_length=2048)
    source_authority: str = Field(min_length=1, max_length=160)
    source_type: KnowledgeSourceType
    jurisdiction: str = Field(min_length=2, max_length=40)
    language: str = Field(min_length=2, max_length=20)
    source_updated_at: date | None = None
    reviewed_at: date
    review_after: date
    tags: list[str] = Field(default_factory=list, max_length=20)
    content_hash: str

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _validate_http_url(value)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _validate_hash(value)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized = [" ".join(item.split()).lower() for item in value if item.strip()]
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_review_window(self) -> "KnowledgeDocument":
        if self.review_after < self.reviewed_at:
            raise ValueError("review_after cannot precede reviewed_at")
        return self

    def freshness(self, *, as_of: date | None = None) -> KnowledgeFreshness:
        current_date = as_of or datetime.now(timezone.utc).date()
        return "stale" if current_date > self.review_after else "current"


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=8, max_length=180)
    document_id: str
    ordinal: int = Field(ge=0)
    heading: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=4000)
    content_hash: str

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _validate_hash(value)


class KnowledgeIngestionBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: KnowledgeDocument
    chunks: list[KnowledgeChunk] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_chunks(self) -> "KnowledgeIngestionBundle":
        if any(chunk.document_id != self.document.document_id for chunk in self.chunks):
            raise ValueError("all chunks must belong to the document")
        ordinals = [chunk.ordinal for chunk in self.chunks]
        if ordinals != list(range(len(self.chunks))):
            raise ValueError("chunk ordinals must be contiguous")
        return self


class KnowledgeIngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    status: KnowledgeIngestionStatus
    chunk_count: int = Field(ge=1)


class KnowledgeEvidenceArtifact(BaseModel):
    """Bounded citation projected from one retrieved knowledge chunk."""

    model_config = ConfigDict(extra="forbid")

    citation_id: str = Field(min_length=8, max_length=200)
    document_id: str
    chunk_id: str
    title: str = Field(min_length=1, max_length=240)
    section: str = Field(min_length=1, max_length=240)
    excerpt: str = Field(min_length=1, max_length=1200)
    source_url: str = Field(min_length=8, max_length=2048)
    source_authority: str = Field(min_length=1, max_length=160)
    jurisdiction: str = Field(min_length=2, max_length=40)
    reviewed_at: date
    review_after: date
    freshness: KnowledgeFreshness
    retrieval_method: KnowledgeRetrievalMethod
    score: float = Field(ge=0)

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _validate_http_url(value)


def build_knowledge_evidence(
    document: KnowledgeDocument,
    chunk: KnowledgeChunk,
    *,
    retrieval_method: KnowledgeRetrievalMethod,
    score: float,
    as_of: date | None = None,
) -> KnowledgeEvidenceArtifact:
    if chunk.document_id != document.document_id:
        raise ValueError("chunk does not belong to document")
    return KnowledgeEvidenceArtifact(
        citation_id=f"knowledge:{chunk.chunk_id}",
        document_id=document.document_id,
        chunk_id=chunk.chunk_id,
        title=document.title,
        section=chunk.heading,
        excerpt=chunk.content[:1200],
        source_url=document.source_url,
        source_authority=document.source_authority,
        jurisdiction=document.jurisdiction,
        reviewed_at=document.reviewed_at,
        review_after=document.review_after,
        freshness=document.freshness(as_of=as_of),
        retrieval_method=retrieval_method,
        score=score,
    )

