"""Protocol implemented by persisted and future external quote providers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from app.models.investments import MarketInstrument, MarketQuoteBatch
from app.models.market_data import (
    MarketAssetType,
    MarketInstrumentData,
    MarketPriceBar,
    MarketProviderStatus,
)


class MarketDataProvider(Protocol):
    def get_latest_quotes(
        self,
        instruments: list[MarketInstrument],
        *,
        as_of: datetime,
    ) -> MarketQuoteBatch: ...


class MarketResearchProvider(Protocol):
    def get_price_history(
        self,
        symbol: str,
        *,
        asset_type: MarketAssetType,
        date_from: date,
        date_to: date,
        currency: str,
    ) -> list[MarketPriceBar]: ...

    def get_instrument_profile(
        self,
        symbol: str,
        *,
        asset_type: MarketAssetType,
        fetched_at: datetime,
    ) -> MarketInstrumentData: ...

    def get_status(self) -> MarketProviderStatus: ...
