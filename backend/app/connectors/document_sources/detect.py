"""Document source detection by magic bytes + filename extension.

Magic bytes classify binaries (PDF, images, zip-based Office); the extension
disambiguates zip-based formats (docx/pptx/xlsx share the PK zip magic) and
identifies plain-text formats (md/txt). xls (legacy) is not supported — users
save as xlsx.
"""

from __future__ import annotations

PDF_MAGIC = b"%PDF"
PK_MAGIC = b"PK\x03\x04"  # docx / pptx / xlsx (zip)


class UnsupportedDocumentType(Exception):
    """Raised when the uploaded file is not a supported document type."""


def detect_document_kind(content: bytes, filename: str = "") -> str:
    """Return the document kind slug: pdf/docx/pptx/xlsx/md/txt/image."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    # Images by magic
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if content[:3] == b"\xff\xd8\xff":  # JPEG
        return "image"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image"
    if content[:4] == b"RIFF" and b"WEBP" in content[:16]:
        return "image"
    if content[:2] == b"BM":  # BMP
        return "image"
    # PDF
    if content[: len(PDF_MAGIC)] == PDF_MAGIC:
        return "pdf"
    # Zip-based Office (docx/pptx/xlsx share PK magic) → disambiguate by extension
    if content[: len(PK_MAGIC)] == PK_MAGIC:
        if ext == "docx":
            return "docx"
        if ext == "pptx":
            return "pptx"
        if ext == "xlsx":
            return "xlsx"
        raise UnsupportedDocumentType(
            f"zip archive needs a .docx/.pptx/.xlsx extension (got '{filename}')"
        )
    # Plain text by extension
    if ext in ("md", "markdown"):
        return "md"
    if ext == "txt":
        return "txt"
    raise UnsupportedDocumentType(
        f"unsupported document type (filename='{filename}', ext='{ext}')"
    )
