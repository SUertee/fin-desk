"""Vision-language provider protocol for ingestion-time image captioning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VLObservation:
    """VL output for one image.

    ``caption`` is the searchable description. MVEP folds visible in-image
    text (tables, charts, labels) into caption; ``ocr_text`` is reserved for a
    future dedicated OCR pass that splits description from raw text.
    """

    caption: str
    ocr_text: str = ""


class VisionProvider(Protocol):
    def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        *,
        prompt: str = "",
    ) -> VLObservation:
        """Return a searchable description for ``image_bytes``."""
