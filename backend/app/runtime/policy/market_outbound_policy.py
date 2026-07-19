"""Deterministic outbound-call governance for external market data."""

from __future__ import annotations

from dataclasses import dataclass

from app.connectors.market_data.errors import MarketDataBudgetExceeded
from app.models.market_data import ExternalCallUsage


@dataclass
class OutboundCallBudget:
    limit: int
    used: int = 0

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("outbound call budget must be positive")
        if self.used < 0 or self.used > self.limit:
            raise ValueError("outbound calls used must be within budget")

    def consume(self) -> None:
        if self.used >= self.limit:
            raise MarketDataBudgetExceeded("market data outbound budget exhausted")
        self.used += 1

    def snapshot(self) -> ExternalCallUsage:
        return ExternalCallUsage(
            budget=self.limit,
            used=self.used,
            remaining=self.limit - self.used,
        )
