"""Document source parsers: detect → parse → Document tree.

MVEP supports PDF/DOCX/PPTX/XLSX/MD/TXT/standalone-image. Each parser returns a
Document tree (text/table/image blocks); image bytes are resolved later by the
ingestion service (VL caption + MinIO).
"""

from __future__ import annotations

from app.connectors.document_sources.detect import (
    UnsupportedDocumentType,
    detect_document_kind,
)
from app.connectors.document_sources.pdf import parse_pdf

__all__ = [
    "detect_document_kind",
    "UnsupportedDocumentType",
    "parse_document",
    "parse_pdf",
]


def parse_document(kind: str, content: bytes):
    """Dispatch to the format-specific parser by ``kind``. Returns a Document.

    PDF here is the no-VL fallback (finalize(extract)); the ingestion service
    drives the full extract→enrich→finalize pipeline for PDFs so low-layout
    pages get VL ordering/heading patching.
    """
    if kind == "pdf":
        return parse_pdf(content)
    if kind == "docx":
        from app.connectors.document_sources.docx import parse_docx

        return parse_docx(content)
    if kind == "pptx":
        from app.connectors.document_sources.pptx import parse_pptx

        return parse_pptx(content)
    if kind == "xlsx":
        from app.connectors.document_sources.excel import parse_excel

        return parse_excel(content)
    if kind == "md":
        from app.connectors.document_sources.markdown import parse_md

        return parse_md(content)
    if kind == "txt":
        from app.connectors.document_sources.plaintext import parse_plaintext

        return parse_plaintext(content)
    if kind == "image":
        from app.connectors.document_sources.image import parse_image

        return parse_image(content)
    raise UnsupportedDocumentType(f"parser for kind '{kind}' not available")
