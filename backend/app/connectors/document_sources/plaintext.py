"""TXT parser: charset detection + blank-line paragraph split → synthetic-root text blocks.

TXT has no encoding metadata (unlike docx/pdf), so we probe the bytes via
charset_normalizer (already pulled in by the openai dependency) before decoding.
Falls back to utf-8 + errors=replace if probing fails.
"""

from __future__ import annotations

from app.knowledge.document_models import Block, Document, Section


def parse_plaintext(content: bytes) -> Document:
    encoding = _detect_encoding(content)
    text = content.decode(encoding, errors="replace")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    blocks = [Block(type="text", content=p) for p in paragraphs]
    return Document(root=Section(level=0, title=None, synthetic=True, blocks=blocks))


def _detect_encoding(content: bytes) -> str:
    """Probe encoding via charset_normalizer (utf-8 fallback)."""
    try:
        from charset_normalizer import from_bytes

        result = from_bytes(content)
        best = result.best() if result else None
        if best and best.encoding:
            return best.encoding
    except Exception:
        pass
    return "utf-8"
