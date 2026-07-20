"""Build a canonical research snapshot from serialized FinDesk histories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.models.market_data import MarketPriceHistory
from research.quant_lab.dataset import build_dataset_snapshot, write_dataset_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    histories = [MarketPriceHistory.model_validate(item) for item in payload]
    snapshot = build_dataset_snapshot(histories)
    target = write_dataset_snapshot(snapshot, args.output)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
