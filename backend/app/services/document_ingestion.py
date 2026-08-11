"""Document ingestion orchestration (chunker + embedding as the substrate).

Pipeline: detect → parse → post-process images (VL caption cached per document
in meta.image_captions) → chunker → embed → one chunk table. Image captions
become chunk_text and are vectorized alongside text; the original oss_key lives
in chunk meta for the agent to presign on demand. P3 swaps the synchronous body
for the async worker; the per-file control flow stays identical.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO

from app.config.settings import AppSettings, get_settings
from app.connectors.document_sources import (
    UnsupportedDocumentType,
    detect_document_kind,
    parse_document,
)
from app.connectors.embeddings.siliconflow_provider import (
    SiliconFlowEmbeddingProvider,
)
from app.connectors.object_storage import MinioObjectStorageProvider
from app.connectors.postgres.user_document_store import UserDocumentStore
from app.connectors.vision import SiliconFlowVisionProvider
from app.knowledge.chunker import chunk_document
from app.knowledge.document_models import Block
from app.knowledge.text_contract import (
    normalize_document_text,
    validate_chunks,
    validate_embeddings,
)


@dataclass(frozen=True)
class IngestionResult:
    document_id: int
    status: str           # 'done' | 'deduped' | 'failed'
    chunk_count: int = 0
    image_count: int = 0
    error: str = ""


_EXT_BY_FORMAT = {
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "GIF": ("gif", "image/gif"),
    "WEBP": ("webp", "image/webp"),
    "BMP": ("bmp", "image/bmp"),
}


def _sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _detect_format(image_bytes: bytes) -> tuple[str, str]:
    from PIL import Image

    try:
        fmt = (Image.open(BytesIO(image_bytes)).format or "PNG").upper()
    except Exception:
        fmt = "PNG"
    return _EXT_BY_FORMAT.get(fmt, ("png", "image/png"))


def _should_caption(image_bytes: bytes, min_area: int) -> bool:
    from PIL import Image

    try:
        img = Image.open(BytesIO(image_bytes))
    except Exception:
        return False
    width, height = img.size
    if width * height < min_area:
        return False
    try:
        colors = img.convert("L").getcolors(maxcolors=256)
    except Exception:
        colors = None
    if colors is not None and len(colors) <= 1:
        return False  # solid-color logo/background
    return True


def _collect_image_blocks(doc) -> list[Block]:
    """DFS-collect every image Block from a Document tree.

    All format parsers produce the same Document shape, so image extraction is
    format-agnostic; this keeps _post_process_images independent of whether the
    source was PDF/DOCX/PPTX/XLSX/standalone-image.
    """
    blocks: list[Block] = []

    def walk(section) -> None:
        for b in section.blocks:
            if b.type == "image":
                blocks.append(b)
        for child in section.children:
            walk(child)

    walk(doc.root)
    return blocks


class DocumentIngestionService:
    def __init__(
        self,
        *,
        object_storage: MinioObjectStorageProvider,
        vision: SiliconFlowVisionProvider,
        embedding_provider: SiliconFlowEmbeddingProvider,
        store: UserDocumentStore,
        settings: AppSettings,
    ) -> None:
        self.object_storage = object_storage
        self.vision = vision
        self.embedding_provider = embedding_provider
        self.store = store
        self.settings = settings

    def ingest(self, candidate) -> IngestionResult:
        content = candidate.content
        file_hash = _sha256_hex(content)
        claim = self.store.claim_document(
            file_hash=file_hash,
            filename=candidate.filename,
            mime_type=candidate.mime_type,
            size_bytes=len(content),
            source_kind=candidate.source_kind,
        )
        if not claim.is_new:
            return IngestionResult(document_id=claim.document_id, status="deduped")

        document_id = claim.document_id
        self.store.mark_ingestion_status(document_id=document_id, status="processing")
        try:
            # Per-document image_captions cache: re-ingestion skips VL/MinIO.
            doc_meta = self.store.get_document_meta(document_id)
            captions_cache = doc_meta.setdefault("image_captions", {})

            kind = detect_document_kind(content, candidate.filename)
            if kind == "pdf":
                # PDF 走完整三阶段：extract → enrich(VL 版式补判) → finalize
                from app.connectors.document_sources.pdf import (
                    enrich_pdf_layout,
                    extract_pdf,
                    finalize_pdf,
                )
                draft = extract_pdf(content)
                enrich_result = enrich_pdf_layout(draft, content, self.vision)
                doc = finalize_pdf(draft, enrich_result.patch)
            else:
                doc = parse_document(kind, content)
            image_blocks = _collect_image_blocks(doc)
            image_count = self._post_process_images(
                image_blocks, file_hash=file_hash, captions_cache=captions_cache
            )

            normalize_document_text(doc)
            raw_chunks = chunk_document(doc)
            validate_chunks(raw_chunks)
            if not raw_chunks:
                raise ValueError("document produced no chunks")

            texts = [c.chunk_text for c in raw_chunks]
            embeddings = self._embed_batched(texts)
            validate_embeddings(embeddings, len(raw_chunks))

            # chunk_text + embedding + meta all land in the one chunk table.
            # chunker's meta already carries type/section_path/page/oss_key.
            chunk_rows = [
                (
                    ordinal,
                    raw_chunks[ordinal].chunk_text,
                    embeddings[ordinal],
                    _sha256_hex(raw_chunks[ordinal].chunk_text),
                    raw_chunks[ordinal].meta,
                )
                for ordinal in range(len(raw_chunks))
            ]
            self.store.replace_chunks(document_id=document_id, chunks=chunk_rows)

            # Persist image_captions cache back to document meta.
            self.store.update_document_meta(document_id, doc_meta)

            self.store.mark_ingestion_status(document_id=document_id, status="done")
            return IngestionResult(
                document_id=document_id,
                status="done",
                chunk_count=len(raw_chunks),
                image_count=image_count,
            )
        except Exception as exc:
            self.store.mark_ingestion_status(
                document_id=document_id, status="failed", error=str(exc)
            )
            return IngestionResult(
                document_id=document_id,
                status="failed",
                error=str(exc)[:500],
            )

    def _embed_batched(self, texts: list[str]) -> list[list[float]]:
        batch_size = max(1, self.settings.knowledge.embedding_batch_size)
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            out.extend(
                self.embedding_provider.embed(
                    texts[i : i + batch_size], purpose="document"
                )
            )
        return out

    def _post_process_images(
        self, image_blocks: list[Block], *, file_hash: str, captions_cache: dict
    ) -> int:
        """Filter, dedup, store, and VL-caption every image block.

        captions_cache is the document's image_captions meta (mutated in place):
        {image_hash: {caption, oss_key, thumb_key}}. A hit reuses caption +
        oss_key and skips both VL and MinIO; the chunker later turns the caption
        into an image chunk (chunk_text=caption, meta.oss_key). image_bytes are
        cleared after this step.
        """
        min_area = self.settings.document_ingestion.image_min_area
        seen: set[str] = set()
        processed = 0
        for block in image_blocks:
            if not block.image_bytes:
                continue
            image_hash = _sha256_hex(block.image_bytes)
            if image_hash in seen or not _should_caption(block.image_bytes, min_area):
                block.image_bytes = None
                continue
            seen.add(image_hash)
            cached = captions_cache.get(image_hash)
            if cached:
                block.caption = cached.get("caption", "")
                block.image_oss_key = cached.get("oss_key", "")
            else:
                ext, mime = _detect_format(block.image_bytes)
                oss_key = f"documents/{file_hash}/images/{image_hash}.{ext}"
                self.object_storage.put_object(oss_key, block.image_bytes, mime)
                observation = self.vision.describe_image(block.image_bytes, mime)
                block.caption = observation.caption
                block.image_oss_key = oss_key
                captions_cache[image_hash] = {
                    "caption": caption,
                    "oss_key": oss_key,
                }
            block.image_bytes = None
            processed += 1
        return processed


@lru_cache(maxsize=1)
def build_document_ingestion_service() -> DocumentIngestionService | None:
    """Construct the ingestion service from current settings, or None when
    object storage or vision is not configured (capability gate)."""
    settings = get_settings()
    if not settings.object_storage.enabled or not settings.vision.enabled:
        return None
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
    vision = SiliconFlowVisionProvider(
        api_key=settings.vision.api_key,
        model_id=settings.vision.model,
        base_url=settings.vision.base_url,
        timeout_seconds=settings.vision.timeout_seconds,
    )
    embedding = SiliconFlowEmbeddingProvider(
        api_key=settings.knowledge.embedding_api_key,
        model_id=settings.knowledge.embedding_model,
        dimension=settings.knowledge.embedding_dimension,
        base_url=settings.knowledge.embedding_base_url,
        timeout_seconds=settings.knowledge.embedding_timeout_seconds,
        max_batch_size=settings.knowledge.embedding_batch_size,
    )
    return DocumentIngestionService(
        object_storage=storage,
        vision=vision,
        embedding_provider=embedding,
        store=UserDocumentStore(),
        settings=settings,
    )
