"""Generic CSV statement source reader.

Fallback parser for simple CSV statements (signed amount column, or paired
income/expense columns). Dedicated sources (Alipay, WeChat) have their own
parsers; everything produces the shared NormalizedTransaction contract.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime

from app.connectors.statement_sources.contracts import (
    NormalizedTransaction,
    ParseReport,
)


class StatementImportError(ValueError):
    """Raised when a statement cannot be parsed into valid transactions."""


DATE_FIELDS = ("date", "transaction_date", "posted_date", "time", "日期", "交易时间")
DESCRIPTION_FIELDS = (
    "description",
    "merchant",
    "counterparty",
    "name",
    "memo",
    "交易对方",
    "商品说明",
    "备注",
)
AMOUNT_FIELDS = ("amount", "金额", "交易金额")
INCOME_FIELDS = ("income", "credit", "收入", "收款")
EXPENSE_FIELDS = ("expense", "debit", "支出", "付款")
CURRENCY_FIELDS = ("currency", "币种")
CATEGORY_FIELDS = ("category", "分类")
PAYMENT_METHOD_FIELDS = ("payment_method", "account", "支付方式", "账户")
REFERENCE_FIELDS = ("reference", "transaction_id", "external_id", "交易订单号", "交易单号")


def _clean_header(value: str | None) -> str:
    return (value or "").strip().lower().replace(" ", "_")


def _first_value(row: dict[str, str], fields: tuple[str, ...]) -> str:
    normalized = {_clean_header(key): value for key, value in row.items()}
    for field in fields:
        value = normalized.get(_clean_header(field))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_date(value: str) -> str:
    text = value.strip()
    if not text:
        raise StatementImportError("Missing transaction date")

    text = text.replace(".", "-").replace("/", "-")
    text = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?$", "", text)
    formats = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m-%d-%Y", "%d-%m-%Y")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", text):
        parts = text[:10].split("-")
        return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    raise StatementImportError(f"Unsupported transaction date: {value}")


def _parse_money(value: str) -> float | None:
    text = value.strip()
    if not text or text in {"-", "—"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = re.sub(r"[,$¥￥\s]", "", text)
    text = text.replace("+", "")
    if not text:
        return None
    amount = float(text)
    return -amount if negative else amount


def _parse_amount(row: dict[str, str]) -> float:
    amount = _parse_money(_first_value(row, AMOUNT_FIELDS))
    if amount is not None:
        return round(amount, 2)

    income = _parse_money(_first_value(row, INCOME_FIELDS))
    expense = _parse_money(_first_value(row, EXPENSE_FIELDS))
    if income is not None and income != 0:
        return round(abs(income), 2)
    if expense is not None and expense != 0:
        return round(-abs(expense), 2)

    raise StatementImportError("Missing transaction amount")


def parse_generic_csv(
    content: bytes | str,
) -> tuple[list[NormalizedTransaction], ParseReport]:
    """Parse common CSV statement rows into the normalized contract."""

    if isinstance(content, bytes):
        from app.connectors.statement_sources.encoding import decode_statement_bytes

        text, encoding = decode_statement_bytes(content)
    else:
        text, encoding = content, "text"

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise StatementImportError("CSV header row is missing")

    report = ParseReport(detected_source="generic_csv", encoding_or_format=encoding)
    transactions: list[NormalizedTransaction] = []
    for index, row in enumerate(reader, start=2):
        if not row or not any(str(value or "").strip() for value in row.values()):
            continue
        report.total_rows += 1
        try:
            date = _parse_date(_first_value(row, DATE_FIELDS))
            amount = _parse_amount(row)
        except Exception as exc:
            report.skip(index, "unparseable_row", f"{row} ({exc})")
            continue
        counterparty = _first_value(row, ("counterparty", "交易对方")) or None
        description = (
            _first_value(row, DESCRIPTION_FIELDS) or counterparty or "Imported transaction"
        )
        transactions.append(
            NormalizedTransaction(
                date=date,
                description=description,
                counterparty=counterparty,
                amount=amount,
                currency=(_first_value(row, CURRENCY_FIELDS) or "CNY").upper(),
                source="generic_csv",
                source_reference=_first_value(row, REFERENCE_FIELDS) or None,
                payment_method=_first_value(row, PAYMENT_METHOD_FIELDS) or None,
                raw_category=_first_value(row, CATEGORY_FIELDS) or None,
                status="completed",
                raw={k: v for k, v in row.items() if v},
            )
        )
        report.parsed_rows += 1

    if not transactions:
        details = "; ".join(
            f"row {s.line_no}: {s.snippet}" for s in report.skipped[:3]
        )
        raise StatementImportError(details or "No valid transaction rows found")

    return transactions, report
