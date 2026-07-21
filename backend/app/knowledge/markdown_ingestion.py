"""Deterministic Markdown ingestion for reviewed knowledge notes."""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterable

from app.knowledge.contracts import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionBundle,
    KnowledgeIngestionResult,
)

REQUIRED_METADATA = {
    "id",
    "title",
    "source_url",
    "source_authority",
    "source_type",
    "jurisdiction",
    "language",
    "reviewed_at",
    "review_after",
}
DEFAULT_CORPUS = Path(__file__).with_name("corpus")


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _normalize_body(value: str) -> str:
    lines = [line.rstrip() for line in value.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    normalized: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                normalized.append("")
            blank = True
        else:
            normalized.append(line)
            blank = False
    return "\n".join(normalized)


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise ValueError("knowledge Markdown requires front matter")
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise ValueError("knowledge Markdown front matter is not closed")
    metadata: dict[str, str] = {}
    for line in normalized[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"invalid front matter line: {line}")
        metadata[key.strip()] = value.strip().strip('"\'')
    missing = sorted(REQUIRED_METADATA - metadata.keys())
    if missing:
        raise ValueError(f"missing knowledge metadata: {', '.join(missing)}")
    body = _normalize_body(normalized[end + 5 :])
    if not body:
        raise ValueError("knowledge Markdown body cannot be empty")
    return metadata, body


def _section_chunks(
    document_id: str,
    title: str,
    body: str,
    *,
    max_chars: int = 1800,
) -> list[KnowledgeChunk]:
    sections: list[tuple[str, list[str]]] = []
    heading = title
    lines: list[str] = []

    def flush() -> None:
        content = _normalize_body("\n".join(lines))
        if content:
            sections.append((heading, content.split("\n\n")))

    for line in body.splitlines():
        if line.startswith("#") and line.lstrip("#").startswith(" "):
            flush()
            heading = line.lstrip("#").strip()
            lines = []
        else:
            lines.append(line)
    flush()

    chunks: list[KnowledgeChunk] = []
    for section_heading, paragraphs in sections:
        current = ""
        for paragraph in paragraphs:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if current and len(candidate) > max_chars:
                chunks.append(_chunk(document_id, len(chunks), section_heading, current))
                current = paragraph
            else:
                current = candidate
        if current:
            chunks.append(_chunk(document_id, len(chunks), section_heading, current))
    if not chunks:
        raise ValueError("knowledge document produced no chunks")
    return chunks


def _chunk(document_id: str, ordinal: int, heading: str, content: str) -> KnowledgeChunk:
    content_hash = _hash(content)
    return KnowledgeChunk(
        chunk_id=f"{document_id}:{ordinal:03d}:{content_hash[:12]}",
        document_id=document_id,
        ordinal=ordinal,
        heading=heading,
        content=content,
        content_hash=content_hash,
    )


def parse_markdown_document(text: str) -> KnowledgeIngestionBundle:
    metadata, body = _parse_front_matter(text)
    tags = [item.strip() for item in metadata.get("tags", "").split(",") if item.strip()]
    document = KnowledgeDocument(
        document_id=metadata["id"],
        title=metadata["title"],
        source_url=metadata["source_url"],
        source_authority=metadata["source_authority"],
        source_type=metadata["source_type"],
        jurisdiction=metadata["jurisdiction"],
        language=metadata["language"],
        source_updated_at=metadata.get("source_updated_at") or None,
        reviewed_at=metadata["reviewed_at"],
        review_after=metadata["review_after"],
        tags=tags,
        content_hash=_hash(body),
    )
    return KnowledgeIngestionBundle(
        document=document,
        chunks=_section_chunks(document.document_id, document.title, body),
    )


def parse_markdown_file(path: Path) -> KnowledgeIngestionBundle:
    return parse_markdown_document(path.read_text(encoding="utf-8"))


def markdown_paths(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*.md")))
        elif path.suffix.lower() == ".md":
            files.append(path)
    return list(dict.fromkeys(files))


def ingest_paths(
    paths: Iterable[Path],
    *,
    saver: Callable[[KnowledgeIngestionBundle], KnowledgeIngestionResult],
) -> list[KnowledgeIngestionResult]:
    return [saver(parse_markdown_file(path)) for path in markdown_paths(paths)]


def _main() -> int:
    from dotenv import load_dotenv

    from app.connectors.postgres.knowledge_store import save_knowledge_bundle_db

    load_dotenv()
    parser = argparse.ArgumentParser(description="Ingest reviewed FinDesk knowledge")
    parser.add_argument("paths", nargs="*", type=Path, default=[DEFAULT_CORPUS])
    args = parser.parse_args()
    results = ingest_paths(args.paths, saver=save_knowledge_bundle_db)
    for result in results:
        print(f"{result.status:9} {result.document_id} ({result.chunk_count} chunks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
