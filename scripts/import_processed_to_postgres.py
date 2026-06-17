#!/usr/bin/env python3
"""
Import normalized statement outputs under storage/processed into local Postgres.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from app.repositories.transactions_repo import replace_latest_analysis_run_db, replace_transactions_db


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_monthly_totals(summary: dict) -> list[dict]:
    items = []
    for month, metrics in sorted(summary.get("by_month", {}).items()):
        items.append(
            {
                "month": month,
                "income": metrics.get("income", 0),
                "expense": metrics.get("expense", 0),
                "net": metrics.get("net", 0),
                "count": metrics.get("count", 0),
            }
        )
    return items


def build_transactions(records: list[dict]) -> list[dict]:
    items = []
    for record in records:
        transaction_time = record["transaction_time"]
        raw_balance = record.get("raw", {}).get("balance")
        balance = None
        if raw_balance not in (None, ""):
            balance = float(str(raw_balance).replace(",", ""))
        items.append(
            {
                "date": transaction_time[:10],
                "month": record["month"],
                "description": record.get("description", ""),
                "counterparty": record.get("counterparty", ""),
                "amount": record.get("amount", 0),
                "gross_amount": record.get("gross_amount", abs(record.get("amount", 0))),
                "currency": record.get("currency", "CNY"),
                "balance": balance,
                "direction": record.get("direction", ""),
                "type": record.get("transaction_type", ""),
                "category": record.get("category", "other"),
                "status": record.get("status", ""),
                "payment_method": record.get("payment_method", ""),
                "external_id": record.get("external_id", ""),
                "merchant_order_id": record.get("merchant_order_id", ""),
                "source": record.get("source", "manual"),
                "source_file": record.get("source_file", ""),
                "source_format": record.get("source_format", ""),
                "note": record.get("note", ""),
                "raw": record.get("raw", {}),
            }
        )
    return items


BANK_KEYWORDS = ["工商银行", "建设银行", "农业银行", "中国银行", "招商银行", "交通银行"]


def mark_duplicates(transactions: list[dict]) -> None:
    """Mark ICBC transactions as duplicates when a matching Alipay/WeChat record
    exists on the same date with the same absolute amount.

    Logic: if Alipay/WeChat paid via a bank card, the bank statement will also
    have that transaction. We keep the Alipay/WeChat record (richer metadata)
    and mark the bank record as duplicate.
    """
    # Build lookup: (date, abs_amount) -> list of non-bank transactions that used a bank card
    via_bank: dict[tuple[str, float], list[dict]] = {}
    for tx in transactions:
        if tx["source"] in ("alipay", "wechat"):
            pm = tx.get("payment_method", "")
            if any(kw in pm for kw in BANK_KEYWORDS):
                key = (tx["date"], round(abs(tx["amount"]), 2))
                via_bank.setdefault(key, []).append(tx)

    dup_count = 0
    for tx in transactions:
        if tx["source"] == "icbc":
            key = (tx["date"], round(abs(tx["amount"]), 2))
            if key in via_bank:
                tx["is_duplicate"] = True
                dup_count += 1

    print(f"Marked {dup_count} ICBC transactions as duplicates")


def main() -> None:
    processed_dir = ROOT / "storage" / "processed"
    transactions_path = processed_dir / "transactions.normalized.json"
    summary_path = processed_dir / "summary.json"

    records = load_json(transactions_path)
    summary = load_json(summary_path)
    # TODO: Replace hardcoded "demo" with configurable value or CLI argument
    user_id = "demo"

    transactions = build_transactions(records)
    mark_duplicates(transactions)
    monthly_totals = build_monthly_totals(summary)
    period_start = min((tx["date"] for tx in transactions), default=None)
    period_end = max((tx["date"] for tx in transactions), default=None)

    ok_tx = replace_transactions_db(user_id, transactions)
    ok_run = replace_latest_analysis_run_db(
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
        monthly_totals=monthly_totals,
        input_payload={
            "source": "storage/processed",
            "files_processed": summary.get("files_processed", 0),
        },
        output_payload=summary,
        source="statement_import",
    )

    if not (ok_tx and ok_run):
        raise SystemExit("Failed to import processed data into Postgres")

    print(f"Imported {len(transactions)} transactions for user_id={user_id}")
    print(f"Imported latest analysis snapshot covering {period_start} to {period_end}")
