"""PostgreSQL persistence for reviewed knowledge documents and chunks."""

from __future__ import annotations

import json

from app.connectors.postgres.connection import get_conn
from app.knowledge.contracts import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionBundle,
    KnowledgeIngestionResult,
    KnowledgeQuery,
    KnowledgeRetrievalResult,
    build_knowledge_evidence,
)
from app.knowledge.retrieval import lexical_terms


class KnowledgeStoreUnavailable(RuntimeError):
    pass


class PostgresLexicalKnowledgeRetriever:
    def retrieve(self, query: KnowledgeQuery) -> KnowledgeRetrievalResult:
        return retrieve_knowledge_lexical_db(query)


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


def retrieve_knowledge_lexical_db(query: KnowledgeQuery) -> KnowledgeRetrievalResult:
    english_terms, cjk_terms = lexical_terms(query.text)
    if not english_terms and not cjk_terms:
        return KnowledgeRetrievalResult(
            query=query.text,
            match_status="no_match",
            artifacts=[],
        )

    score_parts: list[str] = []
    score_params: list[object] = []
    match_parts: list[str] = []
    match_params: list[object] = []
    if english_terms:
        english_query = " OR ".join(english_terms)
        score_parts.append(
            """
            ts_rank_cd(
                c.search_vector
                || to_tsvector('simple', d.title || ' ' || d.tags::text),
                websearch_to_tsquery('simple', %s)
            ) * 4
            """
        )
        score_params.append(english_query)
        match_parts.append(
            """
            (
                c.search_vector
                || to_tsvector('simple', d.title || ' ' || d.tags::text)
            ) @@ websearch_to_tsquery('simple', %s)
            """
        )
        match_params.append(english_query)
    if cjk_terms:
        score_parts.append(
            """
            (SELECT COALESCE(SUM(
                CASE WHEN lower(d.title) LIKE '%%' || term || '%%' THEN 2 ELSE 0 END
                + CASE WHEN lower(c.heading) LIKE '%%' || term || '%%' THEN 2 ELSE 0 END
                + CASE WHEN lower(c.content) LIKE '%%' || term || '%%' THEN 1 ELSE 0 END
            ), 0) FROM unnest(%s::text[]) AS term)
            """
        )
        score_params.append(cjk_terms)
        match_parts.append(
            """
            EXISTS (
                SELECT 1 FROM unnest(%s::text[]) AS term
                WHERE lower(d.title) LIKE '%%' || term || '%%'
                   OR lower(c.heading) LIKE '%%' || term || '%%'
                   OR lower(c.content) LIKE '%%' || term || '%%'
            )
            """
        )
        match_params.append(cjk_terms)

    filters = query.filters
    where_parts = [f"({' OR '.join(match_parts)})"]
    filter_params: list[object] = []
    if not filters.include_stale:
        where_parts.append("d.review_after >= %s")
        filter_params.append(query.as_of)
    if filters.jurisdictions:
        where_parts.append("lower(d.jurisdiction) = ANY(%s::text[])")
        filter_params.append(filters.jurisdictions)
    if filters.languages:
        where_parts.append("lower(d.language) = ANY(%s::text[])")
        filter_params.append(filters.languages)
    if filters.source_types:
        where_parts.append("d.source_type = ANY(%s::text[])")
        filter_params.append(filters.source_types)
    if filters.tags:
        where_parts.append(
            """
            EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(d.tags) AS tag
                WHERE lower(tag) = ANY(%s::text[])
            )
            """
        )
        filter_params.append(filters.tags)

    sql = f"""
        SELECT
            d.document_id, d.title, d.source_url, d.source_authority,
            d.source_type, d.jurisdiction, d.language, d.source_updated_at,
            d.reviewed_at, d.review_after, d.tags, d.content_hash,
            c.chunk_id, c.ordinal, c.heading, c.content, c.content_hash,
            ({' + '.join(score_parts)}) AS lexical_score
        FROM knowledge_chunks c
        JOIN knowledge_documents d ON d.document_id = c.document_id
        WHERE {' AND '.join(where_parts)}
        ORDER BY lexical_score DESC, d.document_id ASC, c.ordinal ASC
        LIMIT %s
    """
    params = [*score_params, *match_params, *filter_params, query.top_k]

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
                retrieval_method="lexical",
                score=round(float(row[17] or 0), 6),
                as_of=query.as_of,
            )
        )
    return KnowledgeRetrievalResult(
        query=query.text,
        match_status="matched" if artifacts else "no_match",
        artifacts=artifacts,
    )
