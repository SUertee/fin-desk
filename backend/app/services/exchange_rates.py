"""Cache-first exchange-rate retrieval with immutable provider snapshots."""

from __future__ import annotations

from datetime import date
from typing import Callable

from app.connectors.exchange_rates.errors import ExchangeRateUnavailable
from app.connectors.exchange_rates.provider import ExchangeRateProvider
from app.models.costing import ExchangeRateSnapshot, normalize_currency
from app.runtime.costing.service import identity_exchange_rate


ExchangeRateReader = Callable[[str, str, date], ExchangeRateSnapshot | None]
ExchangeRateWriter = Callable[[ExchangeRateSnapshot], bool]


class ExchangeRateService:
    def __init__(
        self,
        *,
        provider: ExchangeRateProvider,
        snapshot_reader: ExchangeRateReader,
        snapshot_writer: ExchangeRateWriter,
        max_snapshot_age_days: int = 7,
    ) -> None:
        if max_snapshot_age_days < 0:
            raise ValueError("max snapshot age cannot be negative")
        self.provider = provider
        self.snapshot_reader = snapshot_reader
        self.snapshot_writer = snapshot_writer
        self.max_snapshot_age_days = max_snapshot_age_days

    def get_rate(
        self,
        billing_currency: str,
        reporting_currency: str,
        *,
        on_date: date,
    ) -> ExchangeRateSnapshot:
        billing = normalize_currency(billing_currency)
        reporting = normalize_currency(reporting_currency)
        identity = identity_exchange_rate(billing, reporting, on_date)
        if identity is not None:
            return identity

        persisted = self.snapshot_reader(billing, reporting, on_date)
        if persisted and (on_date - persisted.exchange_rate_date).days <= self.max_snapshot_age_days:
            return persisted

        snapshot = self.provider.get_rate(billing, reporting, on_date=on_date)
        if not self.snapshot_writer(snapshot):
            raise ExchangeRateUnavailable(
                f"exchange-rate snapshot could not be persisted for {billing}/{reporting}"
            )
        return snapshot
