"""Shared normalized output contract for statement source parsers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NormalizedTransaction:
    """One statement row normalized to a source-independent shape.

    ``amount`` is signed: negative for expenses, positive for income,
    refunds, and interest. ``refund_of`` links a refund to the
    ``source_reference`` of the refunded original when derivable.
    """

    date: str  # ISO date
    description: str
    counterparty: str | None
    amount: float
    currency: str
    source: str  # "alipay" | "wechat" | "generic_csv"
    source_reference: str | None
    payment_method: str | None
    raw_category: str | None
    status: str  # "completed" | "refund" | "interest"
    refund_of: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkippedRow:
    line_no: int
    reason_code: str
    snippet: str


@dataclass
class ParseReport:
    detected_source: str
    encoding_or_format: str
    total_rows: int = 0
    parsed_rows: int = 0
    skipped: list[SkippedRow] = field(default_factory=list)

    def skip(self, line_no: int, reason_code: str, snippet: str) -> None:
        self.skipped.append(
            SkippedRow(line_no=line_no, reason_code=reason_code, snippet=snippet[:120])
        )

    def skipped_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.skipped:
            counts[row.reason_code] = counts.get(row.reason_code, 0) + 1
        return counts

    def model_dump(self) -> dict[str, Any]:
        return {
            "detected_source": self.detected_source,
            "encoding_or_format": self.encoding_or_format,
            "total_rows": self.total_rows,
            "parsed_rows": self.parsed_rows,
            "skipped": [
                {
                    "line_no": row.line_no,
                    "reason_code": row.reason_code,
                    "snippet": row.snippet,
                }
                for row in self.skipped
            ],
        }
