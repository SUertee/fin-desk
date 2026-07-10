"""
Bounded finance helpers for agent use.

These functions do not query the database directly. The API layer/runtime passes
profile, transaction, and monthly-total context in explicitly.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.anomalies import detect_anomalies
from app.services.summaries import build_category_summary


def _active_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in transactions if not t.get("is_duplicate")]


def _round_money(value: float) -> float:
    return round(value + 1e-9, 2)


def build_expense_snapshot(
    transactions: list[dict[str, Any]],
    monthly_totals: list[dict[str, Any]],
) -> dict[str, Any]:
    active = _active_transactions(transactions)
    income_total = 0.0
    expense_total = 0.0
    by_category: dict[str, float] = defaultdict(float)

    for txn in active:
        amount = txn.get("amount")
        if not isinstance(amount, (int, float)):
            continue

        if amount > 0:
            income_total += float(amount)
            continue

        spend = abs(float(amount))
        expense_total += spend
        by_category[txn.get("category") or "Uncategorized"] += spend

    top_categories = sorted(
        [
            {"category": category, "amount": _round_money(amount)}
            for category, amount in by_category.items()
        ],
        key=lambda item: item["amount"],
        reverse=True,
    )[:8]

    anomalies = detect_anomalies(active)
    category_summary = build_category_summary(active)

    return {
        "transaction_count": len(active),
        "income_total": _round_money(income_total),
        "expense_total": _round_money(expense_total),
        "net_total": _round_money(income_total - expense_total),
        "top_categories": top_categories,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[:10],
        "category_summary": category_summary,
        "monthly_totals": monthly_totals,
    }


def build_budget_snapshot(
    profile: dict[str, Any],
    transactions: list[dict[str, Any]],
    monthly_totals: list[dict[str, Any]],
) -> dict[str, Any]:
    expense_snapshot = build_expense_snapshot(transactions, monthly_totals)
    monthly_income = float(profile.get("monthly_income") or 0)
    expense_total = float(expense_snapshot["expense_total"])
    expense_ratio = round(expense_total / monthly_income, 3) if monthly_income > 0 else None

    if expense_ratio is None:
        status = "data_limited"
    elif expense_ratio <= 0.5:
        status = "good"
    elif expense_ratio <= 0.8:
        status = "watch"
    else:
        status = "risk"

    return {
        "monthly_income": _round_money(monthly_income),
        "expense_total": expense_snapshot["expense_total"],
        "net_total": expense_snapshot["net_total"],
        "expense_ratio": expense_ratio,
        "status": status,
        "financial_goals": profile.get("financial_goals") or [],
    }


def build_finance_context_payload(
    user_id: str,
    profile: dict[str, Any],
    transactions: list[dict[str, Any]],
    monthly_totals: list[dict[str, Any]],
    chat_history: list[dict[str, Any]],
    memory_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active = _active_transactions(transactions)
    return {
        "user_id": user_id,
        "profile": profile,
        "transactions_sample": active[:80],
        "monthly_totals": monthly_totals,
        "chat_history": chat_history[-10:],
        "memory_context": memory_context or {},
        "expense_snapshot": build_expense_snapshot(active, monthly_totals),
        "budget_snapshot": build_budget_snapshot(profile, active, monthly_totals),
    }
