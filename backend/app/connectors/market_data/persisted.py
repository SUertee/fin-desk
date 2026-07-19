"""Market data provider backed by immutable PostgreSQL quote snapshots."""

from __future__ import annotations

from datetime import datetime

from app.connectors.postgres.investment_store import list_latest_market_quotes_db
from app.models.investments import MarketInstrument, MarketQuoteBatch


class PersistedMarketDataProvider:
    name = "persisted_market_quotes"

    def get_latest_quotes(
        self,
        instruments: list[MarketInstrument],
        *,
        as_of: datetime,
    ) -> MarketQuoteBatch:
        bounded = list(dict.fromkeys(instruments))[:200]
        quotes = list_latest_market_quotes_db(bounded, as_of=as_of, limit=200)
        found = {quote.instrument for quote in quotes}
        return MarketQuoteBatch(
            provider=self.name,
            as_of=as_of,
            quotes=quotes,
            missing=[item for item in bounded if item not in found],
        )
