"""WeChat Pay statement parser.

The standard WeChat Pay export is an XLSX workbook (~17 preamble rows before a
header row starting 交易时间); a CSV variant with ¥-prefixed amounts also
exists. Fully-refunded transactions appear as a PAIR (the 支出 row and a
matching 退款 收入 row, both with status 已全额退款) and both sides must be
excluded, otherwise expense and income totals are inflated.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

from app.connectors.statement_sources.contracts import (
    NormalizedTransaction,
    ParseReport,
)
from app.connectors.statement_sources.csv_reader import StatementImportError
from app.connectors.statement_sources.encoding import decode_statement_bytes

PREAMBLE_MARKER = "微信支付账单明细"
HEADER_FIRST_CELL = "交易时间"

_STATUS_FULLY_REFUNDED = "已全额退款"
_NEUTRAL_DIRECTION = "/"


def is_wechat_csv_statement(text: str) -> bool:
    return PREAMBLE_MARKER in "\n".join(text.splitlines()[:40])


def parse_wechat_xlsx(
    content: bytes,
) -> tuple[list[NormalizedTransaction], ParseReport]:
    import openpyxl

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    except Exception as exc:
        raise StatementImportError(f"Cannot open XLSX statement: {exc}") from exc
    try:
        rows = [list(row) for row in workbook.active.iter_rows(values_only=True)]
    finally:
        workbook.close()
    return _parse_rows(rows, "xlsx")


def parse_wechat_csv(
    content: bytes | str,
) -> tuple[list[NormalizedTransaction], ParseReport]:
    if isinstance(content, bytes):
        text, encoding = decode_statement_bytes(content)
    else:
        text, encoding = content, "text"
    rows = [list(row) for row in csv.reader(io.StringIO(text))]
    return _parse_rows(rows, f"csv/{encoding}")


def _parse_rows(
    rows: list[list[Any]], fmt: str
) -> tuple[list[NormalizedTransaction], ParseReport]:
    header_index = next(
        (
            i
            for i, row in enumerate(rows)
            if row and str(row[0] or "").strip() == HEADER_FIRST_CELL
        ),
        None,
    )
    if header_index is None:
        raise StatementImportError("WeChat statement header row not found")

    header = [str(cell or "").strip() for cell in rows[header_index]]
    report = ParseReport(detected_source="wechat", encoding_or_format=fmt)
    transactions: list[NormalizedTransaction] = []

    for offset, cells in enumerate(rows[header_index + 1 :]):
        line_no = header_index + 2 + offset
        if not any(str(cell or "").strip() for cell in cells):
            continue
        report.total_rows += 1
        row = {
            key: _clean(cells[i]) if i < len(cells) else ""
            for i, key in enumerate(header)
            if key
        }
        snippet = ",".join(str(c or "") for c in cells)[:120]
        try:
            normalized = _normalize_row(row)
        except (ValueError, KeyError) as exc:
            report.skip(line_no, "unparseable_row", f"{snippet} ({exc})")
            continue
        if isinstance(normalized, str):
            report.skip(line_no, normalized, snippet)
            continue
        transactions.append(normalized)
        report.parsed_rows += 1

    if not transactions and not report.skipped:
        raise StatementImportError("No transaction rows found in WeChat statement")
    return transactions, report


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        return "" if text == "/" else text
    return value


def _normalize_row(row: dict[str, Any]) -> NormalizedTransaction | str:
    status = str(row.get("当前状态", "") or "")
    direction = str(row.get("收/支", "") or "")
    amount = _parse_amount(row.get("金额(元)", ""))

    if status == _STATUS_FULLY_REFUNDED:
        # Both sides of a fully-refunded pair (expense + refund income).
        return "fully_refunded_pair"
    if amount == 0:
        return "zero_amount"

    if direction == "支出":
        signed = -amount
    elif direction == "收入":
        signed = amount
    elif direction in ("", _NEUTRAL_DIRECTION):
        # 中性交易: 零钱充值/提现/理财通存取 are transfers, not cash flow.
        return "neutral_transfer"
    else:
        return "unknown_direction"

    counterparty = str(row.get("交易对方", "") or "") or None
    description = str(row.get("商品", "") or "") or counterparty or "WeChat transaction"
    return NormalizedTransaction(
        date=_parse_date(row.get("交易时间")),
        description=description,
        counterparty=counterparty,
        amount=round(signed, 2),
        currency="CNY",
        source="wechat",
        source_reference=str(row.get("交易单号", "") or "") or None,
        payment_method=str(row.get("支付方式", "") or "") or None,
        raw_category=str(row.get("交易类型", "") or "") or None,
        status="completed",
        raw={k: str(v) for k, v in row.items() if v not in (None, "")},
    )


def _parse_amount(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").replace("¥", "").replace("￥", "").replace(",", "").strip()
    if not text:
        raise ValueError("missing 金额(元)")
    return float(text)


def _parse_date(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    text = str(value or "").strip()[:10]
    if len(text) != 10:
        raise ValueError(f"unsupported 交易时间: {value!r}")
    return text.replace("/", "-")
