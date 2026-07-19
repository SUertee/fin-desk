"""Read-only investment research and hypothetical scenario API."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, status

from app.connectors.exchange_rates.errors import ExchangeRateError
from app.connectors.market_data.errors import (
    MarketDataBudgetExceeded,
    MarketDataProviderError,
    MarketDataUnavailable,
)
from app.models.investment_research import (
    InstrumentResearchSnapshot,
    InvestmentScenario,
    InvestmentScenarioDetail,
    InvestmentScenarioRequest,
    InvestmentScenarioValuation,
    ScenarioPositionsRequest,
    WatchlistItem,
    WatchlistItemRequest,
)
from app.models.investments import normalize_symbol
from app.models.market_data import MarketAssetType
from app.services.investment_research_runtime import (
    get_investment_research_service,
)


router = APIRouter(prefix="/investment-research", tags=["investment-research"])
_service = get_investment_research_service()


def _raise_research_error(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, MarketDataUnavailable):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, MarketDataBudgetExceeded):
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if isinstance(exc, (MarketDataProviderError, ExchangeRateError)):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise exc


@router.get("/{user_id}/watchlist", response_model=list[WatchlistItem])
def list_watchlist(user_id: str) -> list[WatchlistItem]:
    return _service.list_watchlist(user_id)


@router.post(
    "/{user_id}/watchlist",
    response_model=WatchlistItem,
    status_code=status.HTTP_201_CREATED,
)
def follow_instrument(
    user_id: str,
    request: WatchlistItemRequest,
) -> WatchlistItem:
    try:
        return _service.follow(user_id, request)
    except Exception as exc:
        _raise_research_error(exc)
        raise


@router.delete("/{user_id}/watchlist/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_instrument(
    user_id: str,
    symbol: str,
    asset_type: MarketAssetType = Query(default="equity"),
) -> None:
    try:
        _service.unfollow(user_id, normalize_symbol(symbol), asset_type)
    except Exception as exc:
        _raise_research_error(exc)
        raise


@router.get(
    "/{user_id}/instruments/{symbol}",
    response_model=InstrumentResearchSnapshot,
)
def get_instrument_research(
    user_id: str,
    symbol: str,
    asset_type: MarketAssetType = Query(default="equity"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    benchmark_symbol: str = Query(default="SPY", min_length=1, max_length=16),
) -> InstrumentResearchSnapshot:
    selected_to = date_to or date.today()
    selected_from = date_from or (selected_to - timedelta(days=90))
    try:
        return _service.get_instrument_research(
            user_id,
            symbol,
            asset_type=asset_type,
            date_from=selected_from,
            date_to=selected_to,
            benchmark_symbol=benchmark_symbol,
        )
    except Exception as exc:
        _raise_research_error(exc)
        raise


@router.get("/{user_id}/scenarios", response_model=list[InvestmentScenario])
def list_scenarios(user_id: str) -> list[InvestmentScenario]:
    return _service.list_scenarios(user_id)


@router.post(
    "/{user_id}/scenarios",
    response_model=InvestmentScenario,
    status_code=status.HTTP_201_CREATED,
)
def create_scenario(
    user_id: str,
    request: InvestmentScenarioRequest,
) -> InvestmentScenario:
    try:
        return _service.create_scenario(user_id, request)
    except Exception as exc:
        _raise_research_error(exc)
        raise


@router.get(
    "/{user_id}/scenarios/{scenario_id}",
    response_model=InvestmentScenarioDetail,
)
def get_scenario(user_id: str, scenario_id: str) -> InvestmentScenarioDetail:
    try:
        return _service.get_scenario(user_id, scenario_id)
    except Exception as exc:
        _raise_research_error(exc)
        raise


@router.put(
    "/{user_id}/scenarios/{scenario_id}/positions",
    response_model=InvestmentScenarioDetail,
)
def replace_scenario_positions(
    user_id: str,
    scenario_id: str,
    request: ScenarioPositionsRequest,
) -> InvestmentScenarioDetail:
    try:
        return _service.replace_positions(user_id, scenario_id, request.positions)
    except Exception as exc:
        _raise_research_error(exc)
        raise


@router.get(
    "/{user_id}/scenarios/{scenario_id}/valuation",
    response_model=InvestmentScenarioValuation,
)
def get_scenario_valuation(
    user_id: str,
    scenario_id: str,
    as_of: datetime | None = Query(default=None),
) -> InvestmentScenarioValuation:
    selected_time = as_of or datetime.now(timezone.utc)
    if selected_time.tzinfo is None or selected_time.utcoffset() is None:
        raise HTTPException(status_code=400, detail="as_of must be timezone-aware")
    if selected_time > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="as_of cannot be in the future")
    try:
        return _service.value_scenario(user_id, scenario_id, as_of=selected_time)
    except Exception as exc:
        _raise_research_error(exc)
        raise


@router.delete(
    "/{user_id}/scenarios/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_scenario(user_id: str, scenario_id: str) -> None:
    try:
        _service.delete_scenario(user_id, scenario_id)
    except Exception as exc:
        _raise_research_error(exc)
        raise
