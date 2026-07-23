"""Source-independent candidate produced by statement intake connectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class StatementCandidate:
    user_id: str
    filename: str
    content: bytes
    channel: Literal["upload", "folder", "email"]
    origin_key: str = ""
    origin_metadata: dict[str, Any] = field(default_factory=dict)
