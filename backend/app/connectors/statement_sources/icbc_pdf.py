"""ICBC (工商银行) debit account history PDF parser.

The e-statement is a text-layer PDF: each record starts with a date line
followed by a time-prefixed detail line; counterparty names and even the
摘要 column can wrap across lines. Amounts are signed (+income / -expense)
and every row carries a running balance.

Accounting boundary: wallet bills (Alipay/WeChat) are the canonical record
for wallet-routed spending. Bank rows whose counterparty is a wallet
processor — pass-through 快捷支付 mirrors, wallet top-ups, 花呗 repayments,
wallet-side transfer mirrors — skip as ``wallet_settlement`` so they never
double-count against imported wallet statements.
"""

from __future__ import annotations

import io
import re

from app.connectors.statement_sources.contracts import (
    NormalizedTransaction,
    ParseReport,
)
from app.connectors.statement_sources.csv_reader import StatementImportError

STATEMENT_MARKER = "中国工商银行借记账户历史明细"

WALLET_SETTLEMENT_MARKERS = ("支付宝", "财付通", "微信", "蚂蚁")

# 摘要 values that move the user's own money between their own accounts
_OWN_TRANSFER_SUMMARIES = ("提现", "微信零钱提现", "ATM存款", "充值", "理财")

_FOOTER_PATTERNS = re.compile(
    r"(下单时间：.*"  # page-end verification block glues onto the last record
    r"|本页(支出|收入)算术合计：[\d,.]+|本页交易笔数：\d*|请扫描二维码|识别明细真伪"
    r"|中国工商银行借记账户历史明细（电子版）|第\s*\d+\s*页|共\s*\d+\s*页"
    r"|卡号\s*\d+\s*户名：\S+\s*起止日期：[\d\- —]+"
    r"|交易日期\s*账号\s*储种\s*序号\s*币种\s*钞汇\s*摘要\s*地区\s*收入/支出金额\s*余额\s*对方户名\s*对方账号\s*渠道)"
)

_RECORD_SPLIT = re.compile(r"\n(?=\d{4}-\d{2}-\d{2}\n\d{2}:\d{2}:\d{2}\s)")

_RECORD = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<account>\d{10,25})\s+(?P<deposit_type>\S+)\s+(?P<seq>\d+)\s+"
    r"(?P<currency>\S+)\s+(?P<cash>钞|汇)\s+(?P<summary>.+?)\s+"
    r"(?P<region>\d{4})\s+(?P<amount>[+-][\d,]+\.\d{2})\s+"
    r"(?P<balance>[\d,]+\.\d{2})\s+(?P<tail>.+)$"
)

_CHANNELS = ("快捷支付", "网上银行", "ATM交易", "批量业务", "其他", "柜面", "手机银行")


def is_icbc_statement(text: str) -> bool:
    return STATEMENT_MARKER in text[:2000]


def parse_icbc_pdf(
    content: bytes,
) -> tuple[list[NormalizedTransaction], ParseReport]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise StatementImportError(f"Cannot read PDF statement: {exc}") from exc

    if STATEMENT_MARKER not in text:
        raise StatementImportError("Not an ICBC account history statement")
    return parse_icbc_text(text)


def parse_icbc_text(text: str) -> tuple[list[NormalizedTransaction], ParseReport]:
    report = ParseReport(detected_source="bank_icbc", encoding_or_format="pdf")
    transactions: list[NormalizedTransaction] = []

    # Wallet bills reference this CARD number tail in payment_method
    # (e.g. 工商银行储蓄卡(6472)); the per-row account column is the internal
    # account number, so the card tail must come from the header.
    card_match = re.search(r"卡号\s*(\d{15,19})", text)
    card_tail = card_match.group(1)[-4:] if card_match else ""

    for chunk in _RECORD_SPLIT.split(text):
        flat = _FOOTER_PATTERNS.sub(" ", " ".join(chunk.split("\n"))).strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}\s", flat):
            continue  # page preamble, not a record
        report.total_rows += 1
        match = _RECORD.match(flat)
        if not match:
            report.skip(report.total_rows, "unparseable_row", flat)
            continue
        normalized = _normalize_record(match, card_tail)
        if isinstance(normalized, str):
            report.skip(report.total_rows, normalized, flat)
            continue
        transactions.append(normalized)
        report.parsed_rows += 1

    if not transactions and not report.skipped:
        raise StatementImportError("No transaction rows found in ICBC statement")
    return transactions, report


def _normalize_record(match: re.Match, card_tail: str) -> NormalizedTransaction | str:
    summary = match["summary"].replace(" ", "")
    amount = float(match["amount"].replace(",", ""))
    balance = float(match["balance"].replace(",", ""))
    name, account, channel = _split_tail(match["tail"])

    if amount == 0:
        return "zero_amount"
    if any(marker in name for marker in WALLET_SETTLEMENT_MARKERS):
        # Wallet bills are canonical for wallet-routed activity.
        return "wallet_settlement"
    if summary in _OWN_TRANSFER_SUMMARIES or summary.startswith("微信零钱提"):
        return "own_transfer"

    if summary == "利息":
        status = "interest"
    elif summary == "退款":
        status = "refund"
    else:
        status = "completed"

    date = match["date"]
    currency = "CNY" if match["currency"] == "人民币" else match["currency"]
    # The PDF has no order ids; date+time+amount+balance is stable and unique
    # per row, which keeps re-imports idempotent.
    reference = f"icbc:{card_tail or match['account'][-4:]}:{date}T{match['time']}:{match['amount']}:{match['balance']}"

    return NormalizedTransaction(
        date=date,
        description=f"{summary}-{name}" if name else summary,
        counterparty=name or None,
        amount=amount,
        currency=currency,
        source="bank_icbc",
        source_reference=reference,
        payment_method=channel or None,
        raw_category=summary,
        status=status,
        raw={
            "summary": summary,
            "counterparty_account": account,
            "channel": channel,
            "balance": balance,
            "time": match["time"],
            "card_tail": card_tail,
        },
    )


def _split_tail(tail: str) -> tuple[str, str, str]:
    """Split '户名 [wraps] 账号 渠道' — the name may contain spaces from
    PDF line wrapping; account and channel are the last two tokens."""

    tokens = tail.split()
    channel = ""
    if tokens and any(tokens[-1].startswith(c) or c in tokens[-1] for c in _CHANNELS):
        channel = tokens.pop()
    account = ""
    if tokens and (re.fullmatch(r"[\dA-Za-z*]+", tokens[-1]) or tokens[-1] == "（空）"):
        account = tokens.pop()
    name = "".join(tokens)
    if name == "（空）":
        name = ""
    if account == "（空）":
        account = ""
    return name, account, channel
