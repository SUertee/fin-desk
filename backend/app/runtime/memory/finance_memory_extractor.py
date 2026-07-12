"""Extract finance session memory from a completed runtime response."""

from __future__ import annotations

from typing import Any

from app.runtime.memory.summarizer import build_conversation_summary


def extract_finance_memory(
    *,
    user_message: str,
    response_payload: dict[str, Any],
    finance_context: dict[str, Any],
    chat_history: list[dict[str, Any]],
) -> dict[str, Any]:
    data = response_payload.get("data") or {}
    findings = data.get("findings") or []
    actions = data.get("actions") or []
    expense = finance_context.get("expense_snapshot") or {}
    budget = finance_context.get("budget_snapshot") or {}
    top_categories = expense.get("top_categories") or []
    top_category = top_categories[0] if top_categories else {}
    monthly_totals = finance_context.get("monthly_totals") or []

    category_name = str(top_category.get("category") or "").strip()
    period = _period_from_monthly_totals(monthly_totals)
    result_bits = []
    if findings:
        result_bits.append(str(findings[0].get("title") or ""))
    if actions:
        result_bits.append(str(actions[0].get("title") or ""))
    if not result_bits:
        result_bits.append(str(response_payload.get("reply") or "")[:240])

    return {
        "last_topic": {
            "capability": _capability_from_message(user_message),
            "focus": category_name or "overall_finance",
            "period": period.get("label", ""),
            "risk_level": str(budget.get("status") or "data_limited"),
        },
        "last_entities": (
            [{"type": "category", "name": category_name}] if category_name else []
        ),
        "last_result_brief": " ".join(bit for bit in result_bits if bit)[:600],
        "last_time_range": period,
        "last_query": _last_query_from_context(finance_context, user_message),
        "conversation_summary": build_conversation_summary(
            [
                *chat_history,
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": str(response_payload.get("reply") or "")},
            ]
        ),
    }


def _last_query_from_context(
    finance_context: dict[str, Any], user_message: str
) -> dict[str, Any] | None:
    """Typed source of truth for follow-up turns.

    Prefers `query_transactions.filters`; returns None when no typed query
    ran so the session-memory writer never erases a previous useful
    last_query with an empty object.
    """

    filters = (finance_context.get("transaction_query") or {}).get("filters") or {}
    if not filters:
        return None
    metric = "expense_share" if "占比" in (user_message or "") else "total"
    return {**{k: v for k, v in filters.items() if v is not None}, "metric": metric}


def _period_from_monthly_totals(monthly_totals: list[dict[str, Any]]) -> dict[str, str]:
    months = sorted(str(item.get("month") or "") for item in monthly_totals if item.get("month"))
    if not months:
        return {}
    return {"start": months[0], "end": months[-1], "label": f"{months[0]} to {months[-1]}"}


def _capability_from_message(message: str) -> str:
    text = (message or "").lower()
    if "budget" in text:
        return "budget_plan"
    if "audit" in text or "risk" in text:
        return "financial_safety_audit"
    if "cash" in text or "flow" in text:
        return "cashflow_forecast"
    return "spending_review"
