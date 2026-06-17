"""OpenAI Agents SDK tool adapters for bounded finance context."""

from __future__ import annotations

from typing import Any

from app.tools.audit_tools import build_audit_review
from app.tools.specialist_tools import build_controlled_specialist_payloads


OPENAI_FINANCE_TOOL_NAMES = [
    "get_finance_context",
    "get_expense_snapshot",
    "get_budget_snapshot",
    "get_anomaly_summary",
    "get_cashflow_summary",
    "analyze_expense_patterns",
    "generate_budget_plan",
    "run_audit_review",
]


def build_openai_finance_tool_payloads(context: dict[str, Any]) -> dict[str, Any]:
    specialist_payloads = build_controlled_specialist_payloads(context)
    audit_review = build_audit_review(context, specialist_payloads)
    return {
        "finance_context": {
            "user_id": context.get("user_id"),
            "profile": context.get("profile", {}),
            "runtime_policy": context.get("runtime_policy", {}),
            "chat_history": context.get("chat_history", []),
        },
        "expense_snapshot": context.get("expense_snapshot", {}),
        "budget_snapshot": context.get("budget_snapshot", {}),
        "anomaly_summary": {
            "anomaly_count": context.get("expense_snapshot", {}).get("anomaly_count", 0),
            "anomalies": context.get("expense_snapshot", {}).get("anomalies", []),
        },
        "cashflow_summary": {
            "monthly_totals": context.get("monthly_totals", []),
            "expense_total": context.get("expense_snapshot", {}).get("expense_total"),
            "income_total": context.get("expense_snapshot", {}).get("income_total"),
            "net_total": context.get("expense_snapshot", {}).get("net_total"),
        },
        **specialist_payloads,
        "audit_review": audit_review,
    }


def build_openai_finance_tools(context: dict[str, Any]) -> list[Any]:
    try:
        from agents import function_tool
    except Exception as exc:
        raise RuntimeError("openai-agents package is not installed") from exc

    payloads = build_openai_finance_tool_payloads(context)

    @function_tool
    def get_finance_context() -> dict:
        """Return scoped user profile, policy, and recent conversation context."""
        return payloads["finance_context"]

    @function_tool
    def get_expense_snapshot() -> dict:
        """Return spending totals, top categories, and duplicate-aware anomalies."""
        return payloads["expense_snapshot"]

    @function_tool
    def get_budget_snapshot() -> dict:
        """Return budget status and expense ratio based on profile and transactions."""
        return payloads["budget_snapshot"]

    @function_tool
    def get_anomaly_summary() -> dict:
        """Return anomaly count and sampled anomalous transactions."""
        return payloads["anomaly_summary"]

    @function_tool
    def get_cashflow_summary() -> dict:
        """Return monthly cashflow totals and current income/expense/net snapshot."""
        return payloads["cashflow_summary"]

    @function_tool
    def analyze_expense_patterns() -> dict:
        """Return a controlled Expense Analyst review with findings and evidence."""
        return payloads["expense_analyst_review"]

    @function_tool
    def generate_budget_plan() -> dict:
        """Return a controlled Budget Coach plan with recommendations and actions."""
        return payloads["budget_coach_plan"]

    @function_tool
    def run_audit_review() -> dict:
        """Return a controlled audit review for risk, limitations, and evidence quality."""
        return payloads["audit_review"]

    return [
        get_finance_context,
        get_expense_snapshot,
        get_budget_snapshot,
        get_anomaly_summary,
        get_cashflow_summary,
        analyze_expense_patterns,
        generate_budget_plan,
        run_audit_review,
    ]
