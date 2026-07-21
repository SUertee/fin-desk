"""Canonical dataset snapshots built from FinDesk market-history contracts."""

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.models.market_data import MarketPriceHistory
from research.quant_lab.contracts import (
    DatasetManifest,
    NormalizedPriceRow,
    ResearchDatasetSnapshot,
    content_sha256,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_dataset_snapshot(
    histories: list[MarketPriceHistory],
    *,
    created_at: datetime | None = None,
) -> ResearchDatasetSnapshot:
    if not histories:
        raise ValueError("at least one market history is required")

    rows: list[NormalizedPriceRow] = []
    seen_symbols: set[str] = set()
    seen_keys: set[tuple[str, object]] = set()
    for history in histories:
        if history.symbol in seen_symbols:
            raise ValueError(f"duplicate history for symbol {history.symbol}")
        seen_symbols.add(history.symbol)
        if not history.bars:
            raise ValueError(f"history for {history.symbol} has no bars")

        previous_period = None
        for bar in history.bars:
            if bar.symbol != history.symbol:
                raise ValueError("bar symbol must match history symbol")
            if bar.asset_type != history.asset_type:
                raise ValueError("bar asset_type must match history asset_type")
            if bar.interval != history.interval:
                raise ValueError("bar interval must match history interval")
            if bar.close.currency != history.currency:
                raise ValueError("bar currency must match history currency")
            if not history.date_from <= bar.period <= history.date_to:
                raise ValueError("bar period must be inside history range")
            if previous_period is not None and bar.period <= previous_period:
                raise ValueError("history bars must be strictly chronological")
            previous_period = bar.period

            key = (history.symbol, bar.period)
            if key in seen_keys:
                raise ValueError("duplicate symbol-date bar")
            seen_keys.add(key)
            rows.append(
                NormalizedPriceRow(
                    symbol=bar.symbol,
                    asset_type=bar.asset_type,
                    period=bar.period,
                    currency=history.currency,
                    open=bar.open.amount,
                    high=bar.high.amount,
                    low=bar.low.amount,
                    close=bar.close.amount,
                    volume=bar.volume,
                    source=bar.source,
                    fetched_at=history.fetched_at,
                )
            )

    rows.sort(key=lambda row: (row.symbol, row.period))
    payload = [row.model_dump(mode="json") for row in rows]
    digest = content_sha256(payload)
    manifest = DatasetManifest(
        snapshot_id=digest[:16],
        content_sha256=digest,
        symbols=sorted({row.symbol for row in rows}),
        sources=sorted({row.source for row in rows}),
        currencies=sorted({row.currency for row in rows}),
        date_from=min(row.period for row in rows),
        date_to=max(row.period for row in rows),
        row_count=len(rows),
        created_at=created_at or _utc_now(),
    )
    return ResearchDatasetSnapshot(manifest=manifest, rows=rows)


def _decimal_text(value) -> str:
    return format(value, "f")


def write_dataset_snapshot(
    snapshot: ResearchDatasetSnapshot,
    output_root: str | Path,
) -> Path:
    """Write immutable Qlib-source CSVs plus a FinDesk manifest."""

    root = Path(output_root)
    target = root / snapshot.manifest.snapshot_id
    manifest_payload = snapshot.manifest.model_dump(mode="json")
    if target.exists():
        existing = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if existing == manifest_payload:
            return target
        raise FileExistsError("dataset snapshot id already exists with different content")

    root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".quant-snapshot-", dir=root))
    try:
        raw_dir = temporary / "raw"
        instrument_dir = temporary / "instruments"
        raw_dir.mkdir()
        instrument_dir.mkdir()

        rows_by_symbol: dict[str, list[NormalizedPriceRow]] = {}
        for row in snapshot.rows:
            rows_by_symbol.setdefault(row.symbol, []).append(row)

        instrument_lines: list[str] = []
        for symbol, rows in sorted(rows_by_symbol.items()):
            csv_path = raw_dir / f"{symbol.lower()}.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    ["date", "open", "high", "low", "close", "volume", "factor"]
                )
                for row in rows:
                    writer.writerow(
                        [
                            row.period.isoformat(),
                            _decimal_text(row.open),
                            _decimal_text(row.high),
                            _decimal_text(row.low),
                            _decimal_text(row.close),
                            "" if row.volume is None else row.volume,
                            _decimal_text(row.factor),
                        ]
                    )
            instrument_lines.append(
                f"{symbol}\t{rows[0].period.isoformat()}\t{rows[-1].period.isoformat()}"
            )

        (instrument_dir / "all.txt").write_text(
            "\n".join(instrument_lines) + "\n",
            encoding="utf-8",
        )
        (temporary / "manifest.json").write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
        return target
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
