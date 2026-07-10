"""Statement source detection from raw uploaded bytes."""

from __future__ import annotations

from app.connectors.statement_sources.alipay_csv import is_alipay_statement
from app.connectors.statement_sources.csv_reader import StatementImportError
from app.connectors.statement_sources.encoding import decode_statement_bytes
from app.connectors.statement_sources.wechat_xlsx import is_wechat_csv_statement

XLSX_MAGIC = b"PK\x03\x04"
PDF_MAGIC = b"%PDF"


def detect_source(filename: str, raw: bytes) -> str:
    """Detect the statement source: icbc_pdf | wechat_xlsx | wechat_csv |
    alipay | generic_csv.

    Detection is signature-ordered: PDF/XLSX magic bytes → WeChat preamble →
    Alipay preamble/header → generic CSV fallback. Undetectable binary input
    raises a typed error rather than importing garbage rows.
    """

    name = (filename or "").lower()
    if raw[:4] == PDF_MAGIC or name.endswith(".pdf"):
        # ICBC is the only PDF source; its parser validates the marker.
        return "icbc_pdf"
    if raw[:4] == XLSX_MAGIC or name.endswith(".xlsx"):
        # WeChat is the only XLSX source; its parser validates the header.
        return "wechat_xlsx"

    try:
        text, _ = decode_statement_bytes(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise StatementImportError(f"Unsupported statement file: {exc}") from exc

    if is_wechat_csv_statement(text):
        return "wechat_csv"
    if is_alipay_statement(text):
        return "alipay"
    return "generic_csv"
