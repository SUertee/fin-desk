"""Exchange-rate provider protocol."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.models.costing import ExchangeRateSnapshot


class ExchangeRateProvider(Protocol):
    def get_rate(
        self,
        billing_currency: str,
        reporting_currency: str,
        *,
        on_date: date,
    ) -> ExchangeRateSnapshot: ...
