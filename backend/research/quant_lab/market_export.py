"""Strict ETF dataset export through FinDesk's market-data service."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.investments import normalize_symbol
from app.models.market_data import MarketPriceHistory
from research.quant_lab.contracts import NormalizedPriceRow, ResearchDatasetSnapshot
from research.quant_lab.dataset import (
    build_dataset_snapshot_from_rows,
    normalize_history_rows,
)


ExportStatus = Literal["completed", "failed"]
IssueCode = Literal[
    "provider_error",
    "no_data",
    "invalid_data",
    "currency_conflict",
    "duplicate_symbol_date",
]
DateChunk = tuple[date, date]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketHistoryService(Protocol):
    def new_budget(self) -> Any: ...

    def get_history(
        self,
        symbol: str,
        *,
        asset_type: Literal["etf"],
        date_from: date,
        date_to: date,
        budget: Any,
    ) -> MarketPriceHistory: ...


class DatasetExportSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbols: list[str] = Field(min_length=1, max_length=100)
    date_from: date
    date_to: date
    chunk_days: int = Field(default=730, ge=1, le=3660)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: list[str]) -> list[str]:
        normalized = [normalize_symbol(symbol) for symbol in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("export symbols must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_range(self) -> "DatasetExportSpec":
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class ExportIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: IssueCode
    symbol: str
    date_from: date
    date_to: date
    detail: str = Field(min_length=1, max_length=240)


class SymbolCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    row_count: int = Field(ge=0)
    date_from: date | None = None
    date_to: date | None = None
    sources: list[str] = Field(default_factory=list)
    currency: str | None = None


class DatasetExportReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["quant-dataset-export-v1"] = "quant-dataset-export-v1"
    status: ExportStatus
    spec: DatasetExportSpec
    created_at: datetime
    price_adjustment_assumption: Literal["provider_default_unverified"] = (
        "provider_default_unverified"
    )
    coverage: list[SymbolCoverage]
    issues: list[ExportIssue] = Field(default_factory=list)
    snapshot_id: str | None = None

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_status(self) -> "DatasetExportReport":
        if self.status == "completed" and (self.issues or not self.snapshot_id):
            raise ValueError("completed export requires a clean snapshot")
        if self.status == "failed" and self.snapshot_id is not None:
            raise ValueError("failed export cannot reference a snapshot")
        return self


def iter_date_chunks(
    date_from: date, date_to: date, chunk_days: int
) -> list[DateChunk]:
    if date_from > date_to:
        raise ValueError("date_from must be on or before date_to")
    if chunk_days < 1:
        raise ValueError("chunk_days must be positive")

    chunks = []
    cursor = date_from
    while cursor <= date_to:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), date_to)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _add_issue(
    issues: list[ExportIssue],
    code: IssueCode,
    symbol: str,
    chunk: DateChunk,
    detail: str,
) -> None:
    issue = ExportIssue(
        code=code,
        symbol=symbol,
        date_from=chunk[0],
        date_to=chunk[1],
        detail=detail[:240],
    )
    if issue not in issues:
        issues.append(issue)


def _normalize_chunk(
    history: MarketPriceHistory,
    symbol: str,
    chunk: DateChunk,
    issues: list[ExportIssue],
) -> list[NormalizedPriceRow]:
    date_from, date_to = chunk
    if (
        history.symbol != symbol
        or history.asset_type != "etf"
        or history.date_from != date_from
        or history.date_to != date_to
    ):
        _add_issue(
            issues,
            "invalid_data",
            symbol,
            chunk,
            "history metadata does not match the requested chunk",
        )
        return []
    if not history.bars:
        _add_issue(issues, "no_data", symbol, chunk, "provider returned no bars")
        return []

    bars = sorted(history.bars, key=lambda item: item.period)
    periods = [bar.period for bar in bars]
    if len(periods) != len(set(periods)):
        _add_issue(
            issues,
            "duplicate_symbol_date",
            symbol,
            chunk,
            "provider returned a duplicate symbol-date",
        )
        return []
    try:
        return normalize_history_rows(history.model_copy(update={"bars": bars}))
    except ValueError as exc:
        _add_issue(issues, "invalid_data", symbol, chunk, str(exc))
        return []


def export_etf_dataset(
    spec: DatasetExportSpec,
    service: MarketHistoryService,
    *,
    created_at: datetime | None = None,
) -> tuple[DatasetExportReport, ResearchDatasetSnapshot | None]:
    report_time = created_at or _utc_now()
    chunks = iter_date_chunks(spec.date_from, spec.date_to, spec.chunk_days)
    rows: list[NormalizedPriceRow] = []
    issues: list[ExportIssue] = []
    coverage: list[SymbolCoverage] = []

    for symbol in sorted(spec.symbols):
        symbol_rows: list[NormalizedPriceRow] = []
        currency = None
        for chunk in chunks:
            try:
                history = service.get_history(
                    symbol,
                    asset_type="etf",
                    date_from=chunk[0],
                    date_to=chunk[1],
                    budget=service.new_budget(),
                )
            except Exception as exc:
                _add_issue(
                    issues,
                    "provider_error",
                    symbol,
                    chunk,
                    f"market history request failed: {type(exc).__name__}",
                )
                continue

            if currency is not None and history.currency != currency:
                _add_issue(
                    issues,
                    "currency_conflict",
                    symbol,
                    chunk,
                    "one symbol returned inconsistent currencies",
                )
                continue

            chunk_rows = _normalize_chunk(history, symbol, chunk, issues)
            if chunk_rows:
                currency = history.currency
            symbol_rows.extend(chunk_rows)
            rows.extend(chunk_rows)

        periods = [row.period for row in symbol_rows]
        coverage.append(
            SymbolCoverage(
                symbol=symbol,
                row_count=len(symbol_rows),
                date_from=min(periods) if periods else None,
                date_to=max(periods) if periods else None,
                sources=sorted({row.source for row in symbol_rows}),
                currency=currency,
            )
        )

    complete = bool(rows) and not issues and all(item.row_count for item in coverage)
    snapshot = (
        build_dataset_snapshot_from_rows(rows, created_at=report_time)
        if complete
        else None
    )
    report = DatasetExportReport(
        status="completed" if complete else "failed",
        spec=spec,
        created_at=report_time,
        coverage=coverage,
        issues=issues,
        snapshot_id=snapshot.manifest.snapshot_id if snapshot else None,
    )
    return report, snapshot


def write_export_report(report: DatasetExportReport, output: str | Path) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target
