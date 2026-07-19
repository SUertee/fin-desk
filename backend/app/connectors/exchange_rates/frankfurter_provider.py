"""Frankfurter v2 adapter pinned to official ECB reference rates."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable

import httpx

from app.connectors.exchange_rates.errors import ExchangeRateProviderError
from app.models.costing import ExchangeRateSnapshot, normalize_currency


HttpGet = Callable[..., httpx.Response]


class FrankfurterExchangeRateProvider:
    def __init__(
        self,
        *,
        base_url: str = "https://api.frankfurter.dev",
        provider: str = "ECB",
        timeout_seconds: int = 10,
        http_get: HttpGet = httpx.get,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.provider = provider.strip().upper()
        self.timeout_seconds = timeout_seconds
        self.http_get = http_get

    def get_rate(
        self,
        billing_currency: str,
        reporting_currency: str,
        *,
        on_date: date,
    ) -> ExchangeRateSnapshot:
        billing = normalize_currency(billing_currency)
        reporting = normalize_currency(reporting_currency)
        if billing == reporting:
            return ExchangeRateSnapshot(
                billing_currency=billing,
                reporting_currency=reporting,
                exchange_rate=Decimal("1"),
                exchange_rate_date=on_date,
                exchange_rate_source="identity",
            )

        try:
            response = self.http_get(
                f"{self.base_url}/v2/rate/{billing}/{reporting}",
                params={"date": on_date.isoformat(), "providers": self.provider},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ExchangeRateProviderError(
                f"exchange-rate provider failed for {billing}/{reporting}"
            ) from exc

        try:
            returned_billing = normalize_currency(payload["base"])
            returned_reporting = normalize_currency(payload["quote"])
            rate = Decimal(str(payload["rate"]))
            rate_date = date.fromisoformat(str(payload["date"]))
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ExchangeRateProviderError(
                "exchange-rate provider returned an invalid contract"
            ) from exc

        if returned_billing != billing or returned_reporting != reporting or rate <= 0:
            raise ExchangeRateProviderError(
                "exchange-rate provider returned a mismatched currency pair"
            )
        if rate_date > on_date:
            raise ExchangeRateProviderError(
                "exchange-rate provider returned a future-dated rate"
            )
        return ExchangeRateSnapshot(
            billing_currency=billing,
            reporting_currency=reporting,
            exchange_rate=rate,
            exchange_rate_date=rate_date,
            exchange_rate_source=f"frankfurter:{self.provider}",
        )
