"""Controlled specialist outputs for CFO-owned agent runs."""

from __future__ import annotations

from typing import Any


def build_expense_analyst_review(context: dict[str, Any]) -> dict[str, Any]:
    snapshot = context.get("expense_snapshot", {})
    top_categories = snapshot.get("top_categories") or []
    anomalies = snapshot.get("anomalies") or []
    transaction_count = int(snapshot.get("transaction_count") or 0)
    expense_total = snapshot.get("expense_total")
    income_total = snapshot.get("income_total")

    findings: list[dict[str, Any]] = []
    evidence: list[str] = []
    limitations: list[str] = []

    if top_categories:
        top = top_categories[0]
        findings.append(
            {
                "title": f"{top.get('category', 'Top category')} is the largest spending category",
                "evidence": [
                    f"{top.get('category', 'Top category')} totals {top.get('amount')}."
                ],
            }
        )
        evidence.extend(
            f"{item.get('category', 'Category')}: {item.get('amount')}"
            for item in top_categories[:3]
        )
    else:
        limitations.append("No spending categories were available.")

    if anomalies:
        findings.append(
            {
                "title": "Potential unusual transactions detected",
                "evidence": [
                    f"{len(anomalies)} anomaly candidates are present in the sampled transaction set."
                ],
            }
        )

    if transaction_count == 0:
        limitations.append("No active transactions were available for expense analysis.")

    return {
        "specialist": "expense_analyst",
        "summary": {
            "transaction_count": transaction_count,
            "expense_total": expense_total,
            "income_total": income_total,
            "anomaly_count": snapshot.get("anomaly_count", len(anomalies)),
        },
        "findings": findings,
        "evidence": evidence,
        "recommendations": [
            "Review the top spending category before changing the budget.",
            "Check anomaly candidates before treating them as recurring behavior.",
        ],
        "confidence": 0.75 if transaction_count else 0.35,
        "limitations": limitations,
    }


def build_budget_coach_plan(context: dict[str, Any]) -> dict[str, Any]:
    snapshot = context.get("budget_snapshot", {})
    profile = context.get("profile", {})
    status = snapshot.get("status") or "data_limited"
    expense_ratio = snapshot.get("expense_ratio")
    goals = snapshot.get("financial_goals") or profile.get("financial_goals") or []
    monthly_income = snapshot.get("monthly_income")
    limitations: list[str] = []

    if expense_ratio is None:
        limitations.append("Monthly income is missing, so expense ratio cannot be calculated.")

    if status == "good":
        priority = "Maintain the current spending pace and automate savings where possible."
        effort = "low"
        impact = "medium"
    elif status == "watch":
        priority = "Set tighter limits on the largest flexible category this month."
        effort = "medium"
        impact = "medium"
    elif status == "risk":
        priority = "Pause non-essential spending until cash flow returns below the risk threshold."
        effort = "medium"
        impact = "high"
    else:
        priority = "Add income and recurring expense data before setting a precise budget."
        effort = "low"
        impact = "medium"

    return {
        "specialist": "budget_coach",
        "summary": {
            "status": status,
            "expense_ratio": expense_ratio,
            "monthly_income": monthly_income,
            "goals": goals,
        },
        "recommendations": [
            priority,
            "Translate the recommendation into one weekly spending limit.",
        ],
        "actions": [
            {
                "title": "Set next-week spending guardrail",
                "rationale": priority,
                "effort": effort,
                "impact": impact,
            }
        ],
        "confidence": 0.78 if expense_ratio is not None else 0.45,
        "limitations": limitations,
    }


def build_controlled_specialist_payloads(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "expense_analyst_review": build_expense_analyst_review(context),
        "budget_coach_plan": build_budget_coach_plan(context),
    }
