"""OpenBB anti-corruption adapter for bounded, read-only market data."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.connectors.market_data.errors import (
    MarketDataProviderError,
    MarketDataTimeout,
    MarketDataUnavailable,
)
from app.models.costing import MoneyAmount, normalize_currency
from app.models.investments import (
    MarketInstrument,
    MarketQuote,
    MarketQuoteBatch,
    normalize_symbol,
)
from app.models.market_data import (
    MarketAssetType,
    MarketInstrumentData,
    MarketPriceBar,
    MarketProviderStatus,
)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {
        key: item
        for key, item in vars(value).items()
        if not key.startswith("_")
    }


def _results(response: Any) -> list[Any]:
    values = getattr(response, "results", None)
    if values is None and isinstance(response, dict):
        values = response.get("results")
    if values is None:
        return []
    return list(values) if isinstance(values, (list, tuple)) else [values]


def _decimal(value: Any, field: str) -> Decimal:
    if value is None:
        raise MarketDataProviderError(f"market provider omitted {field}")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MarketDataProviderError(f"market provider returned invalid {field}") from exc
    if parsed <= 0:
        raise MarketDataProviderError(f"market provider returned non-positive {field}")
    return parsed


def _datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MarketDataProviderError(
                f"market provider returned invalid {field}"
            ) from exc
    else:
        raise MarketDataProviderError(f"market provider omitted {field}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketDataProviderError(f"market provider returned naive {field}")
    return parsed


def _date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise MarketDataProviderError("market provider returned invalid bar date") from exc
    raise MarketDataProviderError("market provider omitted bar date")


class OpenBBMarketDataProvider:
    name = "openbb"
    supported_operations = ["quote", "history", "profile"]
    supported_asset_types = ["equity", "etf"]

    def __init__(
        self,
        *,
        provider: str = "yfinance",
        allowed_providers: tuple[str, ...] = ("yfinance",),
        timeout_seconds: int = 12,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.provider = provider.strip().lower()
        self.allowed_providers = tuple(item.strip().lower() for item in allowed_providers)
        self.timeout_seconds = timeout_seconds
        self._client_factory = client_factory
        self._client: Any | None = None

    @property
    def allowed(self) -> bool:
        return self.provider in self.allowed_providers

    def _load_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.allowed:
            raise MarketDataUnavailable("configured market provider is not allowlisted")
        try:
            if self._client_factory is not None:
                self._client = self._client_factory()
            else:
                from openbb import obb

                self._client = obb
        except Exception as exc:
            raise MarketDataUnavailable(
                "OpenBB equity and provider extensions are unavailable"
            ) from exc
        return self._client

    def _invoke(self, operation: Callable[[Any], Any]) -> Any:
        client = self._load_client()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="openbb")
        future = executor.submit(operation, client)
        try:
            return future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise MarketDataTimeout("market provider request timed out") from exc
        except (MarketDataProviderError, MarketDataUnavailable):
            raise
        except Exception as exc:
            raise MarketDataProviderError("configured market provider request failed") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _source(self, response: Any) -> str:
        provider = getattr(response, "provider", None)
        if provider is None and isinstance(response, dict):
            provider = response.get("provider")
        return f"openbb:{str(provider or self.provider).strip().lower()}"

    def get_status(self) -> MarketProviderStatus:
        if not self.allowed:
            return MarketProviderStatus(
                availability="unavailable",
                configured_provider=self.provider,
                allowed=False,
                supported_operations=self.supported_operations,
                supported_asset_types=self.supported_asset_types,
                detail="configured provider is not allowlisted",
            )
        try:
            self._load_client()
        except MarketDataUnavailable:
            return MarketProviderStatus(
                availability="unavailable",
                configured_provider=self.provider,
                allowed=True,
                supported_operations=self.supported_operations,
                supported_asset_types=self.supported_asset_types,
                detail="OpenBB market extensions are unavailable",
            )
        return MarketProviderStatus(
            availability="available",
            configured_provider=self.provider,
            allowed=True,
            supported_operations=self.supported_operations,
            supported_asset_types=self.supported_asset_types,
        )

    def get_latest_quotes(
        self,
        instruments: list[MarketInstrument],
        *,
        as_of: datetime,
    ) -> MarketQuoteBatch:
        bounded = list(dict.fromkeys(instruments))
        requested = {item.symbol: item for item in bounded}
        response = self._invoke(
            lambda client: client.equity.price.quote(
                symbol=list(requested),
                provider=self.provider,
            )
        )
        source = self._source(response)
        quotes: list[MarketQuote] = []
        for raw in _results(response):
            item = _mapping(raw)
            try:
                symbol = normalize_symbol(item.get("symbol", ""))
            except ValueError:
                continue
            instrument = requested.get(symbol)
            if instrument is None:
                continue
            price = item.get("last_price", item.get("price", item.get("close")))
            timestamp = next(
                (
                    item.get(key)
                    for key in (
                        "last_timestamp",
                        "participant_timestamp",
                        "sip_timestamp",
                        "timestamp",
                    )
                    if item.get(key) is not None
                ),
                None,
            )
            try:
                quote_time = (
                    _datetime(timestamp, "quote timestamp")
                    if timestamp is not None
                    else as_of
                )
                quote = MarketQuote(
                    symbol=symbol,
                    asset_type=instrument.asset_type,
                    price=MoneyAmount(
                        amount=_decimal(price, "last price"),
                        currency=normalize_currency(item.get("currency", "")),
                    ),
                    quote_as_of=quote_time,
                    timestamp_basis=(
                        "provider_time" if timestamp is not None else "retrieval_time"
                    ),
                    source=source,
                    venue=str(item.get("exchange") or item.get("venue") or ""),
                )
            except (ValueError, MarketDataProviderError):
                continue
            if quote.quote_as_of <= as_of:
                quotes.append(quote)
        found = {quote.symbol for quote in quotes}
        return MarketQuoteBatch(
            provider=source,
            as_of=as_of,
            quotes=quotes,
            missing=[item for item in bounded if item.symbol not in found],
        )

    def get_instrument_profile(
        self,
        symbol: str,
        *,
        asset_type: MarketAssetType,
        fetched_at: datetime,
    ) -> MarketInstrumentData:
        normalized = normalize_symbol(symbol)
        response = self._invoke(
            lambda client: client.equity.profile(
                symbol=normalized,
                provider=self.provider,
            )
        )
        records = _results(response)
        if not records:
            raise MarketDataProviderError("market provider returned no instrument profile")
        item = _mapping(records[0])
        name = item.get("name") or item.get("long_name") or item.get("short_name")
        if not name:
            raise MarketDataProviderError("market provider omitted instrument name")
        return MarketInstrumentData(
            symbol=normalized,
            asset_type=asset_type,
            name=str(name),
            venue=str(item.get("exchange") or item.get("venue") or ""),
            currency=normalize_currency(item.get("currency", "")),
            sector=str(item["sector"]) if item.get("sector") else None,
            industry=str(item["industry"]) if item.get("industry") else None,
            country=str(item["country"]) if item.get("country") else None,
            source=self._source(response),
            fetched_at=fetched_at,
        )

    def get_price_history(
        self,
        symbol: str,
        *,
        asset_type: MarketAssetType,
        date_from: date,
        date_to: date,
        currency: str,
    ) -> list[MarketPriceBar]:
        normalized = normalize_symbol(symbol)
        normalized_currency = normalize_currency(currency)
        response = self._invoke(
            lambda client: client.equity.price.historical(
                symbol=normalized,
                start_date=date_from,
                end_date=date_to,
                interval="1d",
                provider=self.provider,
            )
        )
        source = self._source(response)
        bars: list[MarketPriceBar] = []
        for raw in _results(response):
            item = _mapping(raw)
            def money(key: str) -> MoneyAmount:
                return MoneyAmount(
                    amount=_decimal(item.get(key), key),
                    currency=normalized_currency,
                )

            volume = item.get("volume")
            bars.append(
                MarketPriceBar(
                    symbol=normalized,
                    asset_type=asset_type,
                    period=_date(item.get("date")),
                    open=money("open"),
                    high=money("high"),
                    low=money("low"),
                    close=money("close"),
                    volume=int(volume) if volume is not None else None,
                    source=source,
                    venue=str(item.get("exchange") or item.get("venue") or ""),
                )
            )
        return sorted(bars, key=lambda bar: bar.period)
