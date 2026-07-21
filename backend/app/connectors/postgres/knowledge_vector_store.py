"""pgvector persistence and retrieval for reviewed knowledge chunks."""

from __future__ import annotations

from app.connectors.postgres.connection import get_conn
from app.connectors.postgres.knowledge_store import KnowledgeStoreUnavailable
from app.knowledge.contracts import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeQuery,
    KnowledgeRetrievalResult,
    build_knowledge_evidence,
)
from app.knowledge.embeddings import (
    KnowledgeEmbeddingRecord,
    KnowledgeEmbeddingTarget,
    KnowledgeEmbeddingTargetSet,
)


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".12g") for value in vector) + "]"


class PostgresKnowledgeEmbeddingStore:
    def pending_targets(
        self,
        *,
        provider_id: str,
        model_id: str,
        dimension: int,
    ) -> KnowledgeEmbeddingTargetSet:
        with get_conn() as conn:
            if not conn:
                raise KnowledgeStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM knowledge_chunks")
                total_chunks = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT c.chunk_id, c.heading, c.content, c.content_hash
                    FROM knowledge_chunks c
                    LEFT JOIN knowledge_chunk_embeddings e
                      ON e.chunk_id = c.chunk_id
                     AND e.provider_id = %s
                     AND e.model_id = %s
                    WHERE e.chunk_id IS NULL
                       OR e.content_hash <> c.content_hash
                       OR e.dimension <> %s
                    ORDER BY c.document_id, c.ordinal
                    """,
                    (provider_id, model_id, dimension),
                )
                rows = cur.fetchall()
        return KnowledgeEmbeddingTargetSet(
            total_chunks=total_chunks,
            pending=[
                KnowledgeEmbeddingTarget(
                    chunk_id=row[0],
                    content=f"{row[1]}\n{row[2]}",
                    content_hash=row[3],
                )
                for row in rows
            ],
        )

    def save_embeddings(self, records: list[KnowledgeEmbeddingRecord]) -> None:
        if not records:
            return
        with get_conn() as conn:
            if not conn:
                raise KnowledgeStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO knowledge_chunk_embeddings (
                        chunk_id, provider_id, model_id, dimension,
                        embedding, content_hash, embedded_at
                    ) VALUES (%s, %s, %s, %s, %s::vector, %s, NOW())
                    ON CONFLICT (chunk_id, provider_id, model_id) DO UPDATE SET
                        dimension = EXCLUDED.dimension,
                        embedding = EXCLUDED.embedding,
                        content_hash = EXCLUDED.content_hash,
                        embedded_at = NOW()
                    """,
                    [
                        (
                            record.chunk_id,
                            record.provider_id,
                            record.model_id,
                            record.dimension,
                            _vector_literal(record.vector),
                            record.content_hash,
                        )
                        for record in records
                    ],
                )
            conn.commit()

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
        filters = query.filters
        where_parts = [
            "e.provider_id = %s",
            "e.model_id = %s",
            "e.dimension = %s",
            "GREATEST(0, 1 - (e.embedding <=> %s::vector)) >= %s",
        ]
        vector_literal = _vector_literal(query_vector)
        params: list[object] = [
            vector_literal,
            provider_id,
            model_id,
            dimension,
            vector_literal,
            min_score,
        ]
        if not filters.include_stale:
            where_parts.append("d.review_after >= %s")
            params.append(query.as_of)
        if filters.jurisdictions:
            where_parts.append("lower(d.jurisdiction) = ANY(%s::text[])")
            params.append(filters.jurisdictions)
        if filters.languages:
            where_parts.append("lower(d.language) = ANY(%s::text[])")
            params.append(filters.languages)
        if filters.source_types:
            where_parts.append("d.source_type = ANY(%s::text[])")
            params.append(filters.source_types)
        if filters.tags:
            where_parts.append(
                """
                EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text(d.tags) AS tag
                    WHERE lower(tag) = ANY(%s::text[])
                )
                """
            )
            params.append(filters.tags)
        params.append(query.top_k)

        sql = f"""
            SELECT
                d.document_id, d.title, d.source_url, d.source_authority,
                d.source_type, d.jurisdiction, d.language, d.source_updated_at,
                d.reviewed_at, d.review_after, d.tags, d.content_hash,
                c.chunk_id, c.ordinal, c.heading, c.content, c.content_hash,
                GREATEST(0, 1 - (e.embedding <=> %s::vector)) AS vector_score
            FROM knowledge_chunk_embeddings e
            JOIN knowledge_chunks c ON c.chunk_id = e.chunk_id
            JOIN knowledge_documents d ON d.document_id = c.document_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY vector_score DESC, d.document_id, c.ordinal
            LIMIT %s
        """
        with get_conn() as conn:
            if not conn:
                raise KnowledgeStoreUnavailable("database_unavailable")
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        artifacts = []
        for row in rows:
            document = KnowledgeDocument(
                document_id=row[0],
                title=row[1],
                source_url=row[2],
                source_authority=row[3],
                source_type=row[4],
                jurisdiction=row[5],
                language=row[6],
                source_updated_at=row[7],
                reviewed_at=row[8],
                review_after=row[9],
                tags=list(row[10] or []),
                content_hash=row[11],
            )
            chunk = KnowledgeChunk(
                chunk_id=row[12],
                document_id=row[0],
                ordinal=row[13],
                heading=row[14],
                content=row[15],
                content_hash=row[16],
            )
            artifacts.append(
                build_knowledge_evidence(
                    document,
                    chunk,
                    retrieval_method="vector",
                    score=round(float(row[17] or 0), 6),
                    as_of=query.as_of,
                )
            )
        return KnowledgeRetrievalResult(
            query=query.text,
            match_status="matched" if artifacts else "no_match",
            artifacts=artifacts,
        )
