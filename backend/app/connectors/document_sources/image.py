"""Standalone image parser: one image → Document with a single image block.

A directly-uploaded image flows through the same post_process pipeline (VL
caption + MinIO) as embedded images, so it becomes one image chunk whose
chunk_text is its caption and whose meta.oss_key points at the original.
"""

from __future__ import annotations

from app.knowledge.document_models import Block, Document, Section


def parse_image(content: bytes) -> Document:
    root = Section(level=0, title=None, synthetic=True)
    root.blocks.append(Block(type="image", image_bytes=content, page=1))
    return Document(root=root)
