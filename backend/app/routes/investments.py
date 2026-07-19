"""Read-only investment portfolio endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from app.config.settings import get_settings
from app.connectors.market_data import PersistedMarketDataProvider
from app.connectors.postgres.exchange_rate_store import get_exchange_rate_snapshot_db
from app.connectors.postgres.investment_store import (
    list_investment_accounts_db,
    list_investment_positions_db,
)
from app.models.costing import normalize_currency
from app.models.investments import PortfolioSnapshot
from app.services.investment_portfolio import PortfolioService


router = APIRouter(prefix="/investments", tags=["investments"])
_settings = get_settings().investment
_service = PortfolioService(
    account_reader=list_investment_accounts_db,
    position_reader=list_investment_positions_db,
    market_data_provider=PersistedMarketDataProvider(),
    exchange_rate_lookup=get_exchange_rate_snapshot_db,
    stale_after_days=_settings.quote_stale_after_days,
    concentration_threshold_percent=_settings.concentration_threshold_percent,
)


@router.get("/{user_id}/portfolio", response_model=PortfolioSnapshot)
def get_portfolio(
    user_id: str,
    as_of: datetime | None = Query(default=None),
    reporting_currency: str | None = Query(default=None),
) -> PortfolioSnapshot:
    selected_time = as_of or datetime.now(timezone.utc)
    if selected_time.tzinfo is None or selected_time.utcoffset() is None:
        raise HTTPException(status_code=400, detail="as_of must be timezone-aware")
    if selected_time > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="as_of cannot be in the future")
    try:
        selected_currency = normalize_currency(
            reporting_currency or _settings.reporting_currency
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _service.get_snapshot(
        user_id,
        as_of=selected_time,
        reporting_currency=selected_currency,
    )
