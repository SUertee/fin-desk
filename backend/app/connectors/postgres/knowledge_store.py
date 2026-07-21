"""PostgreSQL persistence for reviewed knowledge documents and chunks."""

from __future__ import annotations

import json

from app.connectors.postgres.connection import get_conn
from app.knowledge.contracts import KnowledgeIngestionBundle, KnowledgeIngestionResult


class KnowledgeStoreUnavailable(RuntimeError):
    pass


def save_knowledge_bundle_db(
    bundle: KnowledgeIngestionBundle,
) -> KnowledgeIngestionResult:
    document = bundle.document
    with get_conn() as conn:
        if not conn:
            raise KnowledgeStoreUnavailable("database_unavailable")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash FROM knowledge_documents WHERE document_id = %s",
                (document.document_id,),
            )
            row = cur.fetchone()
            if row and row[0] == document.content_hash:
                return KnowledgeIngestionResult(
                    document_id=document.document_id,
                    status="unchanged",
                    chunk_count=len(bundle.chunks),
                )
            status = "updated" if row else "created"
            cur.execute(
                """
                INSERT INTO knowledge_documents (
                    document_id, title, source_url, source_authority, source_type,
                    jurisdiction, language, source_updated_at, reviewed_at,
                    review_after, tags, content_hash, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW()
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    source_url = EXCLUDED.source_url,
                    source_authority = EXCLUDED.source_authority,
                    source_type = EXCLUDED.source_type,
                    jurisdiction = EXCLUDED.jurisdiction,
                    language = EXCLUDED.language,
                    source_updated_at = EXCLUDED.source_updated_at,
                    reviewed_at = EXCLUDED.reviewed_at,
                    review_after = EXCLUDED.review_after,
                    tags = EXCLUDED.tags,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = NOW()
                """,
                (
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
                    json.dumps(document.tags, ensure_ascii=False),
                    document.content_hash,
                ),
            )
            cur.execute(
                "DELETE FROM knowledge_chunks WHERE document_id = %s",
                (document.document_id,),
            )
            cur.executemany(
                """
                INSERT INTO knowledge_chunks (
                    chunk_id, document_id, ordinal, heading, content, content_hash
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.ordinal,
                        chunk.heading,
                        chunk.content,
                        chunk.content_hash,
                    )
                    for chunk in bundle.chunks
                ],
            )
        conn.commit()
    return KnowledgeIngestionResult(
        document_id=document.document_id,
        status=status,
        chunk_count=len(bundle.chunks),
    )

