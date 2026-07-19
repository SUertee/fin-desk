"""Protocol implemented by persisted and future external quote providers."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.models.investments import MarketInstrument, MarketQuoteBatch


class MarketDataProvider(Protocol):
    def get_latest_quotes(
        self,
        instruments: list[MarketInstrument],
        *,
        as_of: datetime,
    ) -> MarketQuoteBatch: ...
