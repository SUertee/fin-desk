"""Application-scoped construction for market, FX, and research services."""

from __future__ import annotations

from functools import lru_cache

from app.config.settings import get_settings
from app.connectors.exchange_rates.frankfurter_provider import (
    FrankfurterExchangeRateProvider,
)
from app.connectors.market_data.openbb_provider import OpenBBMarketDataProvider
from app.connectors.postgres.exchange_rate_store import (
    get_exchange_rate_snapshot_db,
    save_exchange_rate_snapshot_db,
)
from app.connectors.postgres.investment_research_store import (
    delete_investment_scenario_db,
    delete_watchlist_item_db,
    get_investment_scenario_db,
    list_investment_scenarios_db,
    list_watchlist_items_db,
    replace_scenario_positions_db,
    save_investment_scenario_db,
    save_watchlist_item_db,
)
from app.connectors.postgres.investment_store import save_market_quote_snapshot_db
from app.connectors.postgres.market_data_cache_store import (
    get_market_data_cache_db,
    save_market_data_cache_db,
)
from app.services.exchange_rates import ExchangeRateService
from app.services.investment_research import InvestmentResearchService
from app.services.market_data import MarketDataService


@lru_cache(maxsize=1)
def get_market_data_service() -> MarketDataService:
    settings = get_settings().market_data
    provider = OpenBBMarketDataProvider(
        provider=settings.provider,
        allowed_providers=settings.allowed_providers,
        timeout_seconds=settings.timeout_seconds,
    )
    return MarketDataService(
        quote_provider=provider,
        research_provider=provider,
        cache_reader=get_market_data_cache_db,
        cache_writer=save_market_data_cache_db,
        quote_writer=save_market_quote_snapshot_db,
        quote_ttl_seconds=settings.quote_ttl_seconds,
        history_ttl_seconds=settings.history_ttl_seconds,
        profile_ttl_seconds=settings.profile_ttl_seconds,
        symbol_limit=settings.symbol_limit,
        history_day_limit=settings.history_day_limit,
        outbound_call_budget=settings.outbound_call_budget,
    )


@lru_cache(maxsize=1)
def get_exchange_rate_service() -> ExchangeRateService:
    settings = get_settings().exchange_rate
    provider = FrankfurterExchangeRateProvider(
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
    )
    return ExchangeRateService(
        provider=provider,
        snapshot_reader=get_exchange_rate_snapshot_db,
        snapshot_writer=save_exchange_rate_snapshot_db,
        max_snapshot_age_days=settings.max_snapshot_age_days,
    )


@lru_cache(maxsize=1)
def get_investment_research_service() -> InvestmentResearchService:
    settings = get_settings().investment
    return InvestmentResearchService(
        market_data=get_market_data_service(),
        exchange_rates=get_exchange_rate_service(),
        watchlist_reader=list_watchlist_items_db,
        watchlist_writer=save_watchlist_item_db,
        watchlist_deleter=delete_watchlist_item_db,
        scenario_reader=list_investment_scenarios_db,
        scenario_detail_reader=get_investment_scenario_db,
        scenario_writer=save_investment_scenario_db,
        scenario_position_writer=replace_scenario_positions_db,
        scenario_deleter=delete_investment_scenario_db,
        stale_after_days=settings.quote_stale_after_days,
        concentration_threshold_percent=settings.concentration_threshold_percent,
    )
