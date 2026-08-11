"""Agent-facing tool for vector search over user-uploaded documents.

The chunk table is the substrate: text fragments, tables, and image captions
are all vectorized together. Image hits carry meta.oss_key so this tool can
presign a short-lived preview URL inline; the CFO hands the URL to the response
composer without a second tool round-trip (the runtime's LLM never emits a
tool call, so preview is exercised automatically when this tool returns).
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from app.config.settings import AppSettings, get_settings
from app.connectors.embeddings.siliconflow_provider import (
    SiliconFlowEmbeddingProvider,
)
from app.connectors.object_storage import MinioObjectStorageProvider
from app.connectors.postgres.user_document_store import (
    UserDocumentStore,
    UserDocumentStoreUnavailable,
)
from app.runtime.execution import AgentContext, ToolObservation, ToolSpec


class UserDocumentSearchTool:
    name = "search_user_documents"

    def __init__(
        self,
        *,
        embedding_provider: SiliconFlowEmbeddingProvider,
        store: UserDocumentStore,
        object_storage: MinioObjectStorageProvider,
        settings: AppSettings,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.store = store
        self.object_storage = object_storage
        self.settings = settings

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=(
                "Vector search over the user's uploaded documents "
                "(PDFs, images, research notes). Image hits include a "
                "short-lived preview URL."
            ),
            executor=self.execute,
            owner="knowledge",
            deterministic=False,
        )

    async def execute(self, payload: dict[str, Any]) -> ToolObservation:
        started = perf_counter()
        agent = str(payload.get("agent") or "cfo")
        context = payload.get("context")
        if not isinstance(context, AgentContext):
            return self._failure(
                agent=agent,
                started=started,
                error_class="invalid_tool_input",
                error_message="AgentContext is required",
            )
        query_text = context.effective_message
        if not query_text or len(query_text.strip()) < 2:
            return ToolObservation(
                tool_name=self.name,
                success=True,
                agent=agent,
                purpose="user_document_search",
                result={
                    "query": query_text,
                    "match_status": "no_match",
                    "artifacts": [],
                },
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        try:
            query_vector = self.embedding_provider.embed([query_text], purpose="query")[0]
            hits = self.store.retrieve_vector(
                query_vector=query_vector,
                min_score=self.settings.knowledge.vector_min_score,
                top_k=4,
            )
        except UserDocumentStoreUnavailable:
            return self._failure(
                agent=agent,
                started=started,
                error_class="store_unavailable",
                error_message="User document store is currently unavailable.",
            )
        except Exception as exc:
            return self._failure(
                agent=agent,
                started=started,
                error_class=type(exc).__name__,
                error_message="User document search failed.",
            )

        artifacts: list[dict[str, Any]] = []
        evidence_refs: list[str] = []
        for hit in hits:
            meta = hit.meta or {}
            media_kind = meta.get("type", "text")
            preview_url: str | None = None
            if media_kind == "image":
                oss_key = meta.get("oss_key")
                if oss_key:
                    try:
                        preview_url = self.object_storage.get_presigned_url(oss_key)
                    except Exception:
                        preview_url = None
            citation = f"userdoc:{hit.chunk_id}"
            artifacts.append(
                {
                    "citation_id": citation,
                    "document_id": hit.document_id,
                    "document_filename": hit.filename,
                    "chunk_id": hit.chunk_id,
                    "media_kind": media_kind,
                    "section_path": meta.get("section_path", ""),
                    "page": meta.get("page"),
                    "excerpt": hit.chunk_text[:1200],
                    "score": hit.score,
                    "preview_url": preview_url,
                    "preview_available": preview_url is not None,
                }
            )
            evidence_refs.append(citation)
        return ToolObservation(
            tool_name=self.name,
            success=True,
            agent=agent,
            purpose="user_document_search",
            result={
                "query": query_text,
                "match_status": "matched" if artifacts else "no_match",
                "artifacts": artifacts,
            },
            evidence_refs=evidence_refs,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    def _failure(
        self,
        *,
        agent: str,
        started: float,
        error_class: str,
        error_message: str,
    ) -> ToolObservation:
        return ToolObservation(
            tool_name=self.name,
            success=False,
            agent=agent,
            purpose="user_document_search",
            error_class=error_class,
            error_message=error_message,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )


def build_user_document_search_tool(
    settings: AppSettings | None = None,
) -> UserDocumentSearchTool | None:
    """Construct the tool from current settings, or None when object storage or
    vision is not configured (capability gate)."""
    settings = settings or get_settings()
    if not settings.object_storage.enabled or not settings.vision.enabled:
        return None
    embedding = SiliconFlowEmbeddingProvider(
        api_key=settings.knowledge.embedding_api_key,
        model_id=settings.knowledge.embedding_model,
        dimension=settings.knowledge.embedding_dimension,
        base_url=settings.knowledge.embedding_base_url,
        timeout_seconds=settings.knowledge.embedding_timeout_seconds,
        max_batch_size=settings.knowledge.embedding_batch_size,
    )
    storage = MinioObjectStorageProvider(
        endpoint=settings.object_storage.endpoint,
        access_key=settings.object_storage.access_key,
        secret_key=settings.object_storage.secret_key,
        bucket=settings.object_storage.bucket,
        secure=settings.object_storage.secure,
        external_endpoint=settings.object_storage.external_endpoint,
        external_secure=settings.object_storage.external_secure,
        presign_ttl_seconds=settings.object_storage.presign_ttl_seconds,
    )
    return UserDocumentSearchTool(
        embedding_provider=embedding,
        store=UserDocumentStore(),
        object_storage=storage,
        settings=settings,
    )
