"""Alipay CSV statement parser.

Real Alipay exports are GB18030-encoded CSV with ~22 preamble lines before a
header row starting 交易时间. Direction lives in the 收/支 column; the
不计收支 class mixes refunds, credit repayments, failed repayment attempts,
and interest income, each handled differently.
"""

from __future__ import annotations

import csv
import io
import re

from app.connectors.statement_sources.contracts import (
    NormalizedTransaction,
    ParseReport,
)
from app.connectors.statement_sources.csv_reader import StatementImportError
from app.connectors.statement_sources.encoding import decode_statement_bytes

HEADER_PREFIX = "交易时间,"
PREAMBLE_MARKER = "支付宝"

_STATUS_FAILED = ("还款失败", "失败")
_STATUS_CLOSED = "交易关闭"
_STATUS_REFUND = "退款成功"


def is_alipay_statement(text: str) -> bool:
    head = "\n".join(text.splitlines()[:40])
    return PREAMBLE_MARKER in head and "交易时间,交易分类" in head


def parse_alipay_csv(
    content: bytes | str,
) -> tuple[list[NormalizedTransaction], ParseReport]:
    if isinstance(content, bytes):
        text, encoding = decode_statement_bytes(content)
    else:
        text, encoding = content, "text"

    lines = text.splitlines()
    header_index = next(
        (i for i, line in enumerate(lines) if line.startswith(HEADER_PREFIX)), None
    )
    if header_index is None:
        raise StatementImportError("Alipay statement header row not found")

    reader = csv.reader(io.StringIO("\n".join(lines[header_index:])))
    header = [cell.strip() for cell in next(reader)]
    report = ParseReport(
        detected_source="alipay",
        encoding_or_format=encoding,
        source_summary=_extract_source_summary("\n".join(lines[:header_index])),
    )
    transactions: list[NormalizedTransaction] = []

    for offset, cells in enumerate(reader):
        line_no = header_index + 2 + offset
        if not any(cell.strip() for cell in cells):
            continue
        report.total_rows += 1
        row = {
            key: (cells[i].strip() if i < len(cells) else "")
            for i, key in enumerate(header)
            if key
        }
        snippet = ",".join(cells)[:120]
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
        raise StatementImportError("No transaction rows found in Alipay statement")
    return transactions, report


def _extract_source_summary(preamble: str) -> dict[str, float | int]:
    summary: dict[str, float | int] = {}
    count_match = re.search(r"共\s*(\d+)\s*笔记录", preamble)
    if count_match:
        summary["reported_record_count"] = int(count_match.group(1))
    for label, key in (("收入", "reported_income"), ("支出", "reported_expense")):
        match = re.search(
            rf"{label}[：:]\s*\d+\s*笔\s*([\d,.]+)\s*元",
            preamble,
        )
        if match:
            summary[key] = float(match.group(1).replace(",", ""))
    return summary


def _normalize_row(row: dict[str, str]) -> NormalizedTransaction | str:
    """Return a NormalizedTransaction, or a skip reason code string."""

    status = row.get("交易状态", "")
    direction = row.get("收/支", "")
    amount = float(row.get("金额", "") or 0)
    category = row.get("交易分类", "")

    if any(marker in status for marker in _STATUS_FAILED):
        return "failed_transaction"
    if status == _STATUS_CLOSED:
        # Fully-refunded purchases are retroactively marked 交易关闭; Alipay's
        # own expense summary excludes them, so we skip rather than import.
        return "closed_transaction"
    if amount == 0:
        return "zero_amount"

    if direction == "支出":
        signed, norm_status, refund_of = -amount, "completed", None
    elif direction == "收入":
        signed, norm_status, refund_of = amount, "completed", None
    elif direction == "不计收支":
        if status == _STATUS_REFUND:
            signed, norm_status = amount, "refund"
            refund_of = _refund_parent(row.get("交易订单号", ""))
        elif category == "信用借还":
            # 花呗/借呗 repayments and disbursements are transfers; the
            # underlying purchases were already counted when paid.
            return "credit_transfer"
        elif category == "投资理财":
            if "收益" not in row.get("商品说明", ""):
                # 转入/转出/买入 rows move money between own accounts.
                return "investment_transfer"
            signed, norm_status, refund_of = amount, "interest", None
        else:
            return "neutral_other"
    else:
        return "unknown_direction"

    date = row.get("交易时间", "")[:10]
    if len(date) != 10:
        raise ValueError(f"unsupported 交易时间: {row.get('交易时间', '')!r}")

    counterparty = row.get("交易对方", "") or None
    description = row.get("商品说明", "") or counterparty or "Alipay transaction"
    return NormalizedTransaction(
        date=date,
        description=description,
        counterparty=counterparty,
        amount=round(signed, 2),
        currency="CNY",
        source="alipay",
        source_reference=row.get("交易订单号", "") or None,
        payment_method=row.get("收/付款方式", "") or None,
        raw_category=category or None,
        status=norm_status,
        refund_of=refund_of,
        raw={k: v for k, v in row.items() if v},
    )


def _refund_parent(order_id: str) -> str | None:
    """Refund order ids embed the original as `<original>_<suffix>`."""

    if "_" in order_id:
        return order_id.split("_", 1)[0]
    return None
