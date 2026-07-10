"""Statement source readers for uploaded finance files."""

from app.connectors.statement_sources.alipay_csv import parse_alipay_csv
from app.connectors.statement_sources.contracts import (
    NormalizedTransaction,
    ParseReport,
    SkippedRow,
)
from app.connectors.statement_sources.csv_reader import (
    StatementImportError,
    parse_generic_csv,
)
from app.connectors.statement_sources.detect import detect_source
from app.connectors.statement_sources.icbc_pdf import parse_icbc_pdf
from app.connectors.statement_sources.wechat_xlsx import (
    parse_wechat_csv,
    parse_wechat_xlsx,
)

__all__ = [
    "NormalizedTransaction",
    "ParseReport",
    "SkippedRow",
    "StatementImportError",
    "detect_source",
    "parse_alipay_csv",
    "parse_generic_csv",
    "parse_icbc_pdf",
    "parse_wechat_csv",
    "parse_wechat_xlsx",
]
