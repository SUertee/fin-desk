"""Bounded, read-only external market-data API."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.config.settings import get_settings
from app.connectors.market_data.errors import (
    MarketDataBudgetExceeded,
    MarketDataProviderError,
    MarketDataUnavailable,
)
from app.connectors.market_data.openbb_provider import OpenBBMarketDataProvider
from app.connectors.postgres.investment_store import save_market_quote_snapshot_db
from app.connectors.postgres.market_data_cache_store import (
    get_market_data_cache_db,
    save_market_data_cache_db,
)
from app.models.market_data import (
    MarketAssetType,
    MarketInstrumentProfile,
    MarketPriceHistory,
    MarketProviderStatus,
    MarketQuoteResult,
)
from app.services.market_data import MarketDataService


router = APIRouter(prefix="/market", tags=["market"])
_settings = get_settings().market_data
_provider = OpenBBMarketDataProvider(
    provider=_settings.provider,
    allowed_providers=_settings.allowed_providers,
    timeout_seconds=_settings.timeout_seconds,
)
_service = MarketDataService(
    quote_provider=_provider,
    research_provider=_provider,
    cache_reader=get_market_data_cache_db,
    cache_writer=save_market_data_cache_db,
    quote_writer=save_market_quote_snapshot_db,
    quote_ttl_seconds=_settings.quote_ttl_seconds,
    history_ttl_seconds=_settings.history_ttl_seconds,
    profile_ttl_seconds=_settings.profile_ttl_seconds,
    symbol_limit=_settings.symbol_limit,
    history_day_limit=_settings.history_day_limit,
    outbound_call_budget=_settings.outbound_call_budget,
)


def _raise_market_error(exc: Exception) -> None:
    if isinstance(exc, MarketDataUnavailable):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, MarketDataBudgetExceeded):
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if isinstance(exc, MarketDataProviderError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/quotes", response_model=MarketQuoteResult)
def get_market_quotes(
    symbols: str = Query(min_length=1, max_length=800),
    asset_type: MarketAssetType = Query(default="equity"),
) -> MarketQuoteResult:
    try:
        parsed = [item.strip() for item in symbols.split(",") if item.strip()]
        return _service.get_quotes(
            parsed,
            asset_type=asset_type,
            budget=_service.new_budget(),
        )
    except Exception as exc:
        _raise_market_error(exc)
        raise


@router.get("/history/{symbol}", response_model=MarketPriceHistory)
def get_market_history(
    symbol: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    interval: Literal["1d"] = Query(default="1d"),
    asset_type: MarketAssetType = Query(default="equity"),
) -> MarketPriceHistory:
    del interval
    selected_to = date_to or date.today()
    selected_from = date_from or (selected_to - timedelta(days=30))
    try:
        return _service.get_history(
            symbol,
            asset_type=asset_type,
            date_from=selected_from,
            date_to=selected_to,
            budget=_service.new_budget(),
        )
    except Exception as exc:
        _raise_market_error(exc)
        raise


@router.get("/instruments/{symbol}", response_model=MarketInstrumentProfile)
def get_market_instrument(
    symbol: str,
    asset_type: MarketAssetType = Query(default="equity"),
) -> MarketInstrumentProfile:
    try:
        return _service.get_profile(
            symbol,
            asset_type=asset_type,
            budget=_service.new_budget(),
        )
    except Exception as exc:
        _raise_market_error(exc)
        raise


@router.get("/providers/status", response_model=MarketProviderStatus)
def get_market_provider_status() -> MarketProviderStatus:
    return _service.get_provider_status()
