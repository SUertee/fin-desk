"""Upload contracts for user-uploaded documents.

MVEP keeps uploaded bytes in memory through the ingestion pipeline; a local
inbox spill for very large files is deferred to the P3 async worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DocumentCandidate:
    user_id: str
    filename: str
    content: bytes
    mime_type: str
    source_kind: Literal["upload", "chat_attachment"]
