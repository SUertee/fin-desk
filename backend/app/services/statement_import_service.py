"""Application service for statement import workflows.

Owns everything opinionated about imports: source detection dispatch, mapping
the normalized parser contract onto transaction-store rows, idempotent
re-import skips, cross-source duplicate detection, and persistence. Parsers in
``connectors/statement_sources`` only turn bytes into
``NormalizedTransaction`` rows plus a ``ParseReport``.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.connectors.postgres.statement_import_store import save_statement_import_record_db
from app.connectors.postgres.transactions_store import (
    insert_transactions_db,
    list_external_ids_db,
    list_transactions_window_db,
)
from app.connectors.statement_sources import (
    NormalizedTransaction,
    ParseReport,
    StatementImportError,
    detect_source,
    parse_alipay_csv,
    parse_generic_csv,
    parse_icbc_pdf,
    parse_wechat_csv,
    parse_wechat_xlsx,
)
from app.services.categorizer import rule_categorize

SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".pdf")

# Cross-source dedup thresholds
DEDUP_DATE_WINDOW_DAYS = 1
DEDUP_LOOKBACK_PAD_DAYS = 3
DEDUP_COUNTERPARTY_SIMILARITY = 0.6

# Alipay 交易分类 → canonical categories used by the categorizer/analysis
RAW_CATEGORY_MAP = {
    "交通出行": "transport",
    "餐饮美食": "dining",
    "日用百货": "groceries",
    "爱车养车": "transport",
    "酒店旅游": "travel",
    "文化休闲": "entertainment",
    "运动户外": "entertainment",
    "教育培训": "education",
    "生活服务": "utilities",
    "充值缴费": "utilities",
    "医疗健康": "health",
    "服饰装扮": "shopping",
    "数码电器": "shopping",
    "美容美发": "shopping",
    "母婴亲子": "shopping",
    "宠物": "shopping",
    "公益捐赠": "other",
    "转账红包": "transfer",
    "退款": "refund",
    "投资理财": "investment",
    "信用借还": "transfer",
    "商业服务": "services",
    "其他": "other",
}

_PARSERS = {
    "alipay": parse_alipay_csv,
    "wechat_xlsx": parse_wechat_xlsx,
    "wechat_csv": parse_wechat_csv,
    "icbc_pdf": parse_icbc_pdf,
    "generic_csv": parse_generic_csv,
}

# Bank 摘要 values mapped onto canonical categories
BANK_SUMMARY_CATEGORY_MAP = {
    "消费": "",  # fall through to description rules
    "转账": "transfer",
    "他行汇入": "income",
    "银联入账": "income",
    "资金发放": "income",
    "工资": "income",
    "金融付款": "services",
    "还款": "transfer",
}


@dataclass(frozen=True)
class StatementImportResult:
    ok: bool
    user_id: str
    source_file: str
    imported_count: int
    detected_source: str = ""
    parse_report: dict[str, Any] | None = None
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    already_imported_count: int = 0
    quality_report: dict[str, Any] | None = None
    import_record: dict[str, Any] | None = None
    sample: list[dict[str, Any]] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "user_id": self.user_id,
            "source_file": self.source_file,
            "imported_count": self.imported_count,
            "detected_source": self.detected_source,
            "parse_report": self.parse_report,
            "duplicates": self.duplicates,
            "already_imported_count": self.already_imported_count,
            "quality_report": self.quality_report,
            "import_record": self.import_record,
            "sample": self.sample,
        }


class StatementPersistenceUnavailable(RuntimeError):
    """Raised when parsed import rows cannot be persisted."""


def import_statement_file(
    *,
    user_id: str,
    filename: str,
    content: bytes,
) -> StatementImportResult:
    """Detect, parse, dedup, and persist one uploaded statement file."""

    clean_filename = filename or "statement.csv"
    if not clean_filename.lower().endswith(SUPPORTED_EXTENSIONS):
        _record_failed_import(
            user_id=user_id,
            source_file=clean_filename,
            error="Only CSV and XLSX statements are supported.",
        )
        raise StatementImportError("Only CSV and XLSX statements are supported.")

    try:
        source_key = detect_source(clean_filename, content)
        normalized, report = _PARSERS[source_key](content)
    except StatementImportError as exc:
        _record_failed_import(
            user_id=user_id,
            source_file=clean_filename,
            error=str(exc),
        )
        raise

    # Idempotent re-import: rows whose source_reference is already stored.
    existing_ids = list_external_ids_db(user_id)
    batch_refs = {
        tx.source_reference for tx in normalized if tx.source_reference
    }
    fresh: list[NormalizedTransaction] = []
    seen_in_batch: set[str] = set()
    already_imported = 0
    for tx in normalized:
        ref = tx.source_reference or ""
        if ref and (ref in existing_ids or ref in seen_in_batch):
            already_imported += 1
            report.skip(0, "already_imported", f"{tx.date} {tx.description}")
            continue
        if (
            tx.status == "refund"
            and tx.refund_of
            and tx.refund_of not in batch_refs
            and tx.refund_of not in existing_ids
        ):
            # The refunded original was never counted (e.g. retroactively
            # marked 交易关闭 and skipped), so importing the refund would
            # fabricate income.
            report.skip(0, "refund_original_not_imported", f"{tx.date} {tx.description}")
            continue
        if ref:
            seen_in_batch.add(ref)
        fresh.append(tx)

    rows = [_to_store_row(tx, user_id=user_id, source_file=clean_filename) for tx in fresh]
    duplicates = _mark_cross_source_duplicates(user_id, fresh, rows)

    if rows:
        saved = insert_transactions_db(user_id, rows)
        if not saved:
            _record_failed_import(
                user_id=user_id,
                source_file=clean_filename,
                error="Transaction persistence is not available.",
            )
            raise StatementPersistenceUnavailable(
                "Transaction persistence is not available."
            )

    quality_report = _build_quality_report(
        report=report,
        rows=rows,
        duplicates=duplicates,
        already_imported=already_imported,
    )

    sample = rows[:3]
    import_record = save_statement_import_record_db(
        user_id=user_id,
        source_file=clean_filename,
        source_format=report.detected_source,
        imported_count=len(rows),
        status="succeeded",
        sample=sample,
        quality_report=quality_report,
    )

    return StatementImportResult(
        ok=True,
        user_id=user_id,
        source_file=clean_filename,
        imported_count=len(rows),
        detected_source=report.detected_source,
        parse_report=report.model_dump(),
        duplicates=duplicates,
        already_imported_count=already_imported,
        quality_report=quality_report,
        import_record=import_record,
        sample=sample,
    )


def _build_quality_report(
    *,
    report: ParseReport,
    rows: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    already_imported: int,
) -> dict[str, Any]:
    """Agent-consumable data-quality evidence for this import."""

    skipped_by_reason = report.skipped_by_reason()
    dates = sorted(row["date"] for row in rows) if rows else []
    confident = sum(1 for row in rows if row.get("category") not in ("", "other"))
    missing_counterparty = sum(
        1 for row in rows if not str(row.get("counterparty") or "").strip()
    )

    warnings: list[str] = []
    wallet_settlements = skipped_by_reason.get("wallet_settlement", 0)
    if wallet_settlements:
        warnings.append(
            f"{wallet_settlements} bank rows were skipped as wallet settlements; "
            "wallet-routed spending in this period is only visible after the "
            "matching Alipay/WeChat statements are imported."
        )
    failed = skipped_by_reason.get("failed_transaction", 0)
    if failed:
        warnings.append(f"{failed} failed transaction attempts were excluded from totals.")
    if duplicates:
        warnings.append(
            f"{len(duplicates)} rows were flagged as cross-source duplicates and are "
            "excluded from analysis totals."
        )

    return {
        "source_type": report.detected_source,
        "imported_count": len(rows),
        "skipped_count": len(report.skipped),
        "duplicate_count": len(duplicates),
        "already_imported_count": already_imported,
        "skipped_by_reason": skipped_by_reason,
        "missing_fields": {
            "counterparty": missing_counterparty,
            "category": len(rows) - confident,
        },
        "category_confidence": round(confident / len(rows), 3) if rows else None,
        "date_range": {"from": dates[0], "to": dates[-1]} if dates else None,
        "warnings": warnings,
    }


def _to_store_row(
    tx: NormalizedTransaction, *, user_id: str, source_file: str
) -> dict[str, Any]:
    category, confidence = _categorize(tx)
    return {
        "user_id": user_id,
        "date": tx.date,
        "month": tx.date[:7],
        "description": tx.description,
        "counterparty": tx.counterparty or tx.description,
        "amount": tx.amount,
        "gross_amount": abs(tx.amount),
        "currency": tx.currency.upper(),
        "balance": None,
        "direction": "income" if tx.amount > 0 else "expense",
        "type": "statement_import",
        "category": category,
        "status": tx.status if tx.status != "completed" else "imported",
        "payment_method": tx.payment_method or "",
        "external_id": tx.source_reference or "",
        "merchant_order_id": tx.refund_of or "",
        "source": tx.source,
        "source_file": source_file,
        "source_format": tx.source,
        "note": "",
        "is_duplicate": False,
        "duplicate_reason": "",
        "duplicate_of": "",
        "raw": {
            "row": tx.raw,
            "raw_category": tx.raw_category,
            "refund_of": tx.refund_of,
            "category_confidence": confidence,
        },
    }


def _categorize(tx: NormalizedTransaction) -> tuple[str, float | None]:
    if tx.status == "refund":
        return "refund", None
    if tx.status == "interest":
        return "investment", None
    raw = (tx.raw_category or "").strip()
    if raw in RAW_CATEGORY_MAP:
        return RAW_CATEGORY_MAP[raw], None
    if tx.source == "bank_icbc" and BANK_SUMMARY_CATEGORY_MAP.get(raw):
        return BANK_SUMMARY_CATEGORY_MAP[raw], None
    if tx.source == "generic_csv" and raw:
        # Generic CSVs may carry an explicit category column; pass it through.
        return raw, None
    category, confidence = rule_categorize(
        f"{tx.description} {tx.counterparty or ''} {raw}"
    )
    return category, confidence


def _mark_cross_source_duplicates(
    user_id: str,
    fresh: list[NormalizedTransaction],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flag incoming rows that duplicate stored rows from another source."""

    if not fresh:
        return []
    dates = sorted(tx.date for tx in fresh)
    window_from = _shift_date(dates[0], -DEDUP_LOOKBACK_PAD_DAYS)
    window_to = _shift_date(dates[-1], DEDUP_LOOKBACK_PAD_DAYS)
    stored = [
        row
        for row in list_transactions_window_db(user_id, window_from, window_to)
        if not row.get("is_duplicate")
    ]
    if not stored:
        return []

    duplicates: list[dict[str, Any]] = []
    for tx, row in zip(fresh, rows):
        if tx.amount >= 0:
            continue  # only expenses double-count across wallets
        for candidate in stored:
            if candidate.get("source") == tx.source:
                continue
            if abs(abs(candidate["amount"]) - abs(tx.amount)) > 0.005:
                continue
            reason = _duplicate_reason(tx, candidate)
            if not reason:
                continue
            row["is_duplicate"] = True
            row["duplicate_reason"] = reason
            row["duplicate_of"] = candidate["id"]
            duplicates.append(
                {
                    "date": tx.date,
                    "description": tx.description,
                    "amount": tx.amount,
                    "source": tx.source,
                    "duplicate_of": candidate["id"],
                    "duplicate_of_source": candidate.get("source", ""),
                    "reason": reason,
                }
            )
            break
    return duplicates


def _duplicate_reason(
    tx: NormalizedTransaction, candidate: dict[str, Any]
) -> str | None:
    """Which dedup rule (if any) marks `tx` a duplicate of `candidate`."""

    distance = _date_distance(candidate["date"], tx.date)

    # Card-tail rule: a wallet row paid with a bank card and a same-day bank
    # row for that card are the same money regardless of counterparty naming
    # (bank statements often show the acquirer, not the merchant).
    if distance == 0:
        wallet_tail = _card_tail(tx.payment_method)
        candidate_source = candidate.get("source", "")
        if (
            wallet_tail
            and tx.source in ("alipay", "wechat")
            and candidate_source.startswith("bank")
            and f":{wallet_tail}:" in (candidate.get("external_id") or "")
        ):
            return "card_paid_wallet_matches_bank"
        bank_tail = (tx.raw or {}).get("card_tail", "")
        if (
            bank_tail
            and tx.source.startswith("bank")
            and candidate_source in ("alipay", "wechat")
            and bank_tail == _card_tail(candidate.get("payment_method"))
        ):
            return "card_paid_wallet_matches_bank"

    # Name rule: amount + close date + similar counterparty across sources.
    if distance <= DEDUP_DATE_WINDOW_DAYS and _counterparty_matches(
        tx.counterparty or tx.description,
        candidate.get("counterparty") or candidate.get("description") or "",
    ):
        return "cross_source_amount_date_counterparty"
    return None


def _card_tail(payment_method: str | None) -> str:
    match = re.search(r"[（(](\d{4})[)）]", payment_method or "")
    return match.group(1) if match else ""


def _normalize_name(value: str) -> str:
    return re.sub(r"[\s\(\)（）\-_·.,，。/\\*]+", "", value or "").lower()


def _counterparty_matches(left: str, right: str) -> bool:
    a, b = _normalize_name(left), _normalize_name(right)
    if not a or not b:
        return False
    if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= DEDUP_COUNTERPARTY_SIMILARITY


def _date_distance(left: str, right: str) -> int:
    return abs((date.fromisoformat(left) - date.fromisoformat(right)).days)


def _shift_date(value: str, days: int) -> str:
    return (date.fromisoformat(value) + timedelta(days=days)).isoformat()


def _record_failed_import(*, user_id: str, source_file: str, error: str) -> None:
    suffix = source_file.rsplit(".", 1)[-1].lower() if "." in source_file else ""
    save_statement_import_record_db(
        user_id=user_id,
        source_file=source_file,
        source_format=suffix if suffix in ("csv", "xlsx") else "unsupported",
        imported_count=0,
        status="failed",
        error=error,
        sample=[],
    )
