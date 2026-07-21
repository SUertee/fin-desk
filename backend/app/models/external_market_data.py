"""Bounded contracts for market evidence returned by external tool providers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.market_data import MarketAssetType


class ExternalMarketHistoryArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["external-market-history/v1"] = (
        "external-market-history/v1"
    )
    status: Literal["available", "unavailable"]
    provider: Literal["mcp:vibe_trading"] = "mcp:vibe_trading"
    tool_name: Literal["get_market_data"] = "get_market_data"
    symbol: str = Field(min_length=1, max_length=20)
    provider_symbol: str = Field(min_length=1, max_length=24)
    asset_type: MarketAssetType
    date_from: date
    date_to: date
    interval: Literal["1D"] = "1D"
    source_requested: str = Field(min_length=1, max_length=40)
    bar_count: int = Field(default=0, ge=0, le=250)
    first_close: Decimal | None = None
    last_close: Decimal | None = None
    latest_as_of: str | None = Field(default=None, max_length=40)
    period_return_percent: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=5)
    truncated: bool = False
    fetched_at: datetime
    evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    reason: str = Field(default="", max_length=240)
    trade_actions_allowed: Literal[False] = False
