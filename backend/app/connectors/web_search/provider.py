"""Protocol implemented by external search adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.models.web_research import WebSearchProviderResult, WebSearchProviderStatus


class WebSearchProvider(Protocol):
    def get_status(self) -> WebSearchProviderStatus: ...

    def search(
        self,
        query: str,
        *,
        domains: list[str],
        max_results: int,
        topic: str,
        fetched_at: datetime,
    ) -> WebSearchProviderResult: ...
