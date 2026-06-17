"""Controlled audit outputs for finance agent responses."""

from __future__ import annotations

from typing import Any


def _collect_specialist_limitations(specialist_payloads: dict[str, Any]) -> list[str]:
    limitations: list[str] = []
    for payload in specialist_payloads.values():
        if not isinstance(payload, dict):
            continue
        for limitation in payload.get("limitations") or []:
            if isinstance(limitation, str) and limitation not in limitations:
                limitations.append(limitation)
    return limitations


def _minimum_specialist_confidence(specialist_payloads: dict[str, Any]) -> float | None:
    confidences: list[float] = []
    for payload in specialist_payloads.values():
        if not isinstance(payload, dict):
            continue
        confidence = payload.get("confidence")
        if isinstance(confidence, (int, float)):
            confidences.append(float(confidence))
    return min(confidences) if confidences else None


def build_audit_review(
    context: dict[str, Any],
    specialist_payloads: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = context.get("runtime_policy") or {}
    expense_snapshot = context.get("expense_snapshot") or {}
    budget_snapshot = context.get("budget_snapshot") or {}
    specialist_payloads = specialist_payloads or {}

    warnings: list[str] = []
    limitations = _collect_specialist_limitations(specialist_payloads)

    transaction_count = int(expense_snapshot.get("transaction_count") or 0)
    has_monthly_totals = bool(context.get("monthly_totals"))
    risk_level = policy.get("risk_level") or "low"

    if transaction_count == 0:
        warnings.append("No active transactions were available for evidence.")
        limitations.append("Transaction-based conclusions are data limited.")

    if not has_monthly_totals:
        limitations.append("Monthly trend context is unavailable.")

    if budget_snapshot.get("expense_ratio") is None:
        limitations.append("Budget confidence is limited because monthly income is missing.")

    if risk_level == "high":
        warnings.append("This request may involve investment or high-risk financial guidance.")

    if policy.get("allow_market_context"):
        warnings.append("Market context is general information, not personalized investment advice.")

    min_confidence = _minimum_specialist_confidence(specialist_payloads)
    if min_confidence is not None and min_confidence < 0.5:
        warnings.append("At least one specialist output has low confidence.")

    if warnings or limitations or risk_level == "high":
        status = "data_limited" if transaction_count == 0 else "needs_review"
    else:
        status = "verified"

    confidence = 0.82
    if status == "needs_review":
        confidence = 0.62
    if status == "data_limited":
        confidence = 0.42
    if min_confidence is not None:
        confidence = min(confidence, max(0.0, min_confidence))

    combined_warnings = warnings + [
        limitation for limitation in limitations if limitation not in warnings
    ]

    return {
        "specialist": "auditor",
        "audit": {
            "confidence": round(confidence, 2),
            "status": status,
            "warnings": combined_warnings,
        },
        "warnings": warnings,
        "limitations": limitations,
    }
