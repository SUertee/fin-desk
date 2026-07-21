"""Export an audited ETF dataset through FinDesk's market-data service."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from research.quant_lab.dataset import write_dataset_snapshot
from research.quant_lab.market_export import (
    DatasetExportSpec,
    export_etf_dataset,
    write_export_report,
)


DEFAULT_SYMBOLS = "SPY,QQQ,TLT,GLD,VNQ"


def get_market_data_service():
    """Load the same local environment bootstrap used by the FastAPI entrypoint."""

    load_dotenv()
    from app.services.investment_research_runtime import (
        get_market_data_service as build_market_data_service,
    )

    return build_market_data_service()


def _symbols(value: str) -> list[str]:
    symbols = [symbol.strip() for symbol in value.split(",") if symbol.strip()]
    if not symbols:
        raise argparse.ArgumentTypeError(
            "at least one comma-separated symbol is required"
        )
    return symbols


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a strict, content-addressed ETF research dataset.",
    )
    parser.add_argument("--symbols", type=_symbols, default=_symbols(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--date-from", type=date.fromisoformat, default=date(2020, 1, 1)
    )
    parser.add_argument(
        "--date-to", type=date.fromisoformat, default=date(2025, 12, 31)
    )
    parser.add_argument("--chunk-days", type=int, default=730)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/quant_research/datasets"),
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    spec = DatasetExportSpec(
        symbols=args.symbols,
        date_from=args.date_from,
        date_to=args.date_to,
        chunk_days=args.chunk_days,
    )
    report, snapshot = export_etf_dataset(spec, get_market_data_service())

    snapshot_path = None
    if snapshot is not None:
        snapshot_path = write_dataset_snapshot(snapshot, args.output)
    report_path = write_export_report(
        report,
        args.report or args.output / "latest-export-report.json",
    )
    print(
        json.dumps(
            {
                "status": report.status,
                "snapshot_path": str(snapshot_path) if snapshot_path else None,
                "report_path": str(report_path),
                "issue_count": len(report.issues),
            },
            sort_keys=True,
        )
    )
    return 0 if report.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
