"""Deterministic admission policy for prepared statement imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.services.statement_import_service import PreparedStatementImport

_BLOCKING_SKIP_REASONS = {"unparseable_row", "unknown_direction"}
_EXPLICIT_DUPLICATE_REASONS = {
    "card_paid_wallet_matches_bank",
    "cross_source_amount_date_counterparty",
}


@dataclass(frozen=True)
class QualityGateDecision:
    action: Literal["auto_commit", "review_required", "duplicate"]
    reasons: list[str] = field(default_factory=list)


def evaluate_statement_quality(
    prepared: PreparedStatementImport,
    *,
    auto_commit: bool,
) -> QualityGateDecision:
    if not prepared.rows and prepared.already_imported_count > 0:
        return QualityGateDecision("duplicate", ["all_rows_already_imported"])

    reasons: list[str] = []
    skipped = prepared.quality_report.get("skipped_by_reason", {})
    if _BLOCKING_SKIP_REASONS.intersection(skipped):
        reasons.append("parser_uncertainty")
    if not prepared.rows:
        reasons.append("no_importable_transactions")

    reconciliation = prepared.quality_report.get("reconciliation", {})
    if reconciliation.get("status") != "matched":
        reasons.append(f"reconciliation_{reconciliation.get('status', 'not_available')}")

    duplicate_reasons = {
        str(item.get("reason") or "") for item in prepared.duplicates
    }
    if duplicate_reasons - _EXPLICIT_DUPLICATE_REASONS:
        reasons.append("ambiguous_duplicate_relationship")
    if not auto_commit:
        reasons.append("auto_commit_disabled")

    if reasons:
        return QualityGateDecision("review_required", reasons)
    return QualityGateDecision("auto_commit")
