from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.models.costing import MoneyAmount
from app.models.market_data import (
    ExternalCallUsage,
    MarketCacheMetadata,
    MarketPriceBar,
    MarketPriceHistory,
)
from research.cli import export_etf_dataset as export_cli
from research.quant_lab.market_export import (
    DatasetExportSpec,
    export_etf_dataset,
    iter_date_chunks,
)


NOW = datetime(2026, 7, 21, 2, 0, tzinfo=timezone.utc)


def _bar(symbol: str, period: date, currency: str = "USD") -> MarketPriceBar:
    price = MoneyAmount(amount="100", currency=currency)
    return MarketPriceBar(
        symbol=symbol,
        asset_type="etf",
        period=period,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1000,
        source="openbb:test",
    )


def _history(
    symbol: str,
    date_from: date,
    date_to: date,
    *,
    currency: str = "USD",
    extra_bars: list[MarketPriceBar] | None = None,
    reverse: bool = False,
) -> MarketPriceHistory:
    bars = [
        _bar(symbol, date_from + timedelta(days=offset), currency)
        for offset in range((date_to - date_from).days + 1)
    ]
    bars.extend(extra_bars or [])
    if reverse:
        bars.reverse()
    return MarketPriceHistory(
        symbol=symbol,
        asset_type="etf",
        provider="openbb:test",
        currency=currency,
        date_from=date_from,
        date_to=date_to,
        fetched_at=NOW,
        bars=bars,
        cache=MarketCacheMetadata(
            cache_hit=False,
            cache_key=f"export-{symbol.lower()}-{date_from.isoformat()}-0000000000000000",
            provider="openbb:test",
            fetched_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
        external_calls=ExternalCallUsage(budget=2, used=2, remaining=0),
    )


class FakeMarketService:
    def __init__(self, handler):
        self.handler = handler
        self.budgets = []
        self.calls = []

    def new_budget(self):
        budget = object()
        self.budgets.append(budget)
        return budget

    def get_history(self, symbol, *, asset_type, date_from, date_to, budget):
        self.calls.append((symbol, asset_type, date_from, date_to, budget))
        return self.handler(symbol, date_from, date_to)


def _spec(**overrides) -> DatasetExportSpec:
    values = {
        "symbols": ["SPY", "QQQ"],
        "date_from": date(2025, 1, 1),
        "date_to": date(2025, 1, 8),
        "chunk_days": 4,
    }
    values.update(overrides)
    return DatasetExportSpec(**values)


def test_date_chunks_are_closed_and_non_overlapping():
    assert iter_date_chunks(date(2025, 1, 1), date(2025, 1, 10), 4) == [
        (date(2025, 1, 1), date(2025, 1, 4)),
        (date(2025, 1, 5), date(2025, 1, 8)),
        (date(2025, 1, 9), date(2025, 1, 10)),
    ]


def test_complete_export_is_deterministic_and_uses_one_budget_per_chunk():
    first_service = FakeMarketService(
        lambda symbol, start, end: _history(symbol, start, end)
    )
    second_service = FakeMarketService(
        lambda symbol, start, end: _history(symbol, start, end, reverse=True)
    )

    first_report, first_snapshot = export_etf_dataset(
        _spec(), first_service, created_at=NOW
    )
    second_report, second_snapshot = export_etf_dataset(
        _spec(symbols=["QQQ", "SPY"]),
        second_service,
        created_at=NOW + timedelta(hours=1),
    )

    assert first_report.status == second_report.status == "completed"
    assert first_snapshot is not None and second_snapshot is not None
    assert first_snapshot.manifest.content_sha256 == (
        second_snapshot.manifest.content_sha256
    )
    assert len(first_service.calls) == len(first_service.budgets) == 4
    assert all(
        call[-1] is budget
        for call, budget in zip(first_service.calls, first_service.budgets)
    )


def test_provider_failure_withholds_the_snapshot():
    def handler(symbol, start, end):
        if symbol == "SPY" and start == date(2025, 1, 1):
            raise TimeoutError
        return _history(symbol, start, end)

    report, snapshot = export_etf_dataset(
        _spec(), FakeMarketService(handler), created_at=NOW
    )

    assert report.status == "failed"
    assert snapshot is None
    assert {issue.code for issue in report.issues} == {"provider_error"}
    assert next(item for item in report.coverage if item.symbol == "SPY").row_count == 4


def test_invalid_currency_range_and_duplicate_data_are_explicit():
    def handler(symbol, start, end):
        if symbol == "SPY" and start == date(2025, 1, 1):
            return _history(symbol, start, end, extra_bars=[_bar(symbol, start)])
        if symbol == "SPY" and start == date(2025, 1, 5):
            return _history(
                symbol,
                start,
                end,
                extra_bars=[_bar(symbol, end + timedelta(days=1))],
            )
        currency = "CNY" if symbol == "QQQ" and start == date(2025, 1, 5) else "USD"
        return _history(symbol, start, end, currency=currency)

    report, snapshot = export_etf_dataset(
        _spec(), FakeMarketService(handler), created_at=NOW
    )

    assert report.status == "failed"
    assert snapshot is None
    assert {issue.code for issue in report.issues} == {
        "invalid_data",
        "currency_conflict",
        "duplicate_symbol_date",
    }


def test_cli_writes_one_strict_snapshot_and_report(monkeypatch, tmp_path):
    service = FakeMarketService(lambda symbol, start, end: _history(symbol, start, end))
    output = tmp_path / "datasets"
    monkeypatch.setattr(export_cli, "get_market_data_service", lambda: service)
    monkeypatch.setattr(
        "sys.argv",
        [
            "export_etf_dataset",
            "--symbols",
            "SPY",
            "--date-from",
            "2025-01-01",
            "--date-to",
            "2025-01-02",
            "--output",
            str(output),
        ],
    )

    assert export_cli.main() == 0
    assert (output / "latest-export-report.json").exists()
    assert len([path for path in output.iterdir() if path.is_dir()]) == 1
