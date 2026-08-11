"""PostgreSQL persistence for user-uploaded documents.

Two-table design (chunker + embedding as the RAG substrate):
- knowledge_user_documents: file metadata + per-document image_captions cache
  in meta (so re-ingestion never re-runs VL/MinIO for an already-captioned image).
- knowledge_user_chunks: chunker output (text/table/image caption) + embedding +
  meta all in one table. An image is a chunk whose meta.type='image' and whose
  chunk_text is the VL caption; the original oss_key/thumb_key live in meta so
  the agent can presign a preview URL on demand.

File-level dedup uses file_hash ON CONFLICT. Independent from the reviewed
knowledge_* tables (user documents carry no review/jurisdiction authority).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.connectors.postgres.connection import get_conn


class UserDocumentStoreUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class UserDocumentClaim:
    """Result of the file-level dedup insert."""

    document_id: int
    is_new: bool
    ingestion_status: str


@dataclass(frozen=True)
class UserChunkHit:
    """A retrieved chunk: text/caption + meta (carries oss_key for images) + source filename."""

    chunk_id: int
    document_id: int
    chunk_text: str
    meta: dict
    filename: str
    retrieval_method: str
    score: float


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".12g") for value in vector) + "]"


class UserDocumentStore:
    def claim_document(
        self,
        *,
        file_hash: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        source_kind: str,
        title: str = "",
        language: str = "",
    ) -> UserDocumentClaim:
        """File-level dedup (秒传): same hash → same document row.

        ON CONFLICT DO UPDATE lets us read the row back and detect a real insert
        via ``xmax = 0``; a hit returns is_new=False so the caller skips the
        entire parse/VL/embed pipeline.
        """
        with get_conn() as conn:
            if not conn:
                raise UserDocumentStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO knowledge_user_documents (
                        file_hash, filename, mime_type, size_bytes, source_kind,
                        ingestion_status, title, language
                    ) VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)
                    ON CONFLICT (file_hash) DO UPDATE SET updated_at = NOW()
                    RETURNING document_id, ingestion_status, (xmax = 0) AS is_new
                    """,
                    (file_hash, filename, mime_type, size_bytes, source_kind, title, language),
                )
                row = cur.fetchone()
            conn.commit()
        return UserDocumentClaim(
            document_id=row[0],
            is_new=bool(row[2]),
            ingestion_status=row[1],
        )

    def mark_ingestion_status(
        self,
        *,
        document_id: int,
        status: str,
        error: str = "",
    ) -> None:
        with get_conn() as conn:
            if not conn:
                raise UserDocumentStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                if status == "processing":
                    cur.execute(
                        """
                        UPDATE knowledge_user_documents
                        SET ingestion_status = 'processing',
                            ingestion_started_at = NOW(),
                            updated_at = NOW()
                        WHERE document_id = %s
                        """,
                        (document_id,),
                    )
                elif status == "done":
                    cur.execute(
                        """
                        UPDATE knowledge_user_documents
                        SET ingestion_status = 'done',
                            ingestion_finished_at = NOW(),
                            ingestion_error = '',
                            updated_at = NOW()
                        WHERE document_id = %s
                        """,
                        (document_id,),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE knowledge_user_documents
                        SET ingestion_status = 'failed',
                            ingestion_error = %s,
                            ingestion_attempts = ingestion_attempts + 1,
                            updated_at = NOW()
                        WHERE document_id = %s
                        """,
                        (error[:500], document_id),
                    )
            conn.commit()

    def get_document_meta(self, document_id: int) -> dict:
        """Read meta (image_captions cache) for a document."""
        with get_conn() as conn:
            if not conn:
                raise UserDocumentStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT meta FROM knowledge_user_documents WHERE document_id = %s",
                    (document_id,),
                )
                row = cur.fetchone()
        return dict(row[0]) if row and row[0] else {}

    def update_document_meta(self, document_id: int, meta: dict) -> None:
        """Write back meta (image_captions cache) after post_process."""
        with get_conn() as conn:
            if not conn:
                raise UserDocumentStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE knowledge_user_documents
                    SET meta = %s::jsonb, updated_at = NOW()
                    WHERE document_id = %s
                    """,
                    (json.dumps(meta, ensure_ascii=False), document_id),
                )
            conn.commit()

    def replace_chunks(self, *, document_id: int, chunks: list[tuple]) -> None:
        """Idempotent replace: DELETE old chunks then INSERT new in one tx.

        Each tuple: (ordinal, chunk_text, embedding, content_hash, meta_dict).
        chunk_text + embedding + meta land in the one chunk table; a failure
        rolls back so retries are clean.
        """
        with get_conn() as conn:
            if not conn:
                raise UserDocumentStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM knowledge_user_chunks WHERE document_id = %s",
                    (document_id,),
                )
                for ordinal, chunk_text, embedding, content_hash, meta_dict in chunks:
                    cur.execute(
                        """
                        INSERT INTO knowledge_user_chunks (
                            document_id, ordinal, chunk_text, embedding, content_hash, meta
                        ) VALUES (%s, %s, %s, %s::vector, %s, %s::jsonb)
                        """,
                        (
                            document_id,
                            ordinal,
                            chunk_text,
                            _vector_literal(embedding),
                            content_hash,
                            json.dumps(meta_dict, ensure_ascii=False),
                        ),
                    )
            conn.commit()

    def retrieve_vector(
        self,
        *,
        query_vector: list[float],
        min_score: float,
        top_k: int,
    ) -> list[UserChunkHit]:
        """Cosine retrieval over the one chunk table.

        meta carries oss_key/thumb_key for image chunks, so no image-table JOIN
        is needed; the caller decides whether to presign based on meta.type.
        """
        vector_literal = _vector_literal(query_vector)
        sql = """
            SELECT
                c.chunk_id, c.document_id, c.chunk_text, c.meta,
                d.filename,
                GREATEST(0, 1 - (c.embedding <=> %s::vector)) AS score
            FROM knowledge_user_chunks c
            JOIN knowledge_user_documents d ON d.document_id = c.document_id
            WHERE GREATEST(0, 1 - (c.embedding <=> %s::vector)) >= %s
            ORDER BY score DESC, c.document_id, c.ordinal
            LIMIT %s
        """
        params = [vector_literal, vector_literal, min_score, top_k]
        with get_conn() as conn:
            if not conn:
                raise UserDocumentStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [
            UserChunkHit(
                chunk_id=row[0],
                document_id=row[1],
                chunk_text=row[2],
                meta=dict(row[3]) if row[3] else {},
                filename=row[4] or "",
                retrieval_method="vector",
                score=round(float(row[5] or 0), 6),
            )
            for row in rows
        ]

    def list_documents(self) -> list[dict]:
        with get_conn() as conn:
            if not conn:
                raise UserDocumentStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT document_id, filename, mime_type, size_bytes,
                           source_kind, ingestion_status, title, created_at
                    FROM knowledge_user_documents
                    ORDER BY created_at DESC, document_id DESC
                    """
                )
                rows = cur.fetchall()
        return [
            {
                "document_id": row[0],
                "filename": row[1],
                "mime_type": row[2],
                "size_bytes": row[3],
                "source_kind": row[4],
                "ingestion_status": row[5],
                "title": row[6],
                "created_at": row[7].isoformat() if row[7] else None,
            }
            for row in rows
        ]

    def delete_document(self, *, document_id: int) -> bool:
        """Delete a document row; chunks cascade."""
        with get_conn() as conn:
            if not conn:
                raise UserDocumentStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM knowledge_user_documents WHERE document_id = %s",
                    (document_id,),
                )
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted
