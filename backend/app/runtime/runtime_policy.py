"""Deterministic policy for CFO-first orchestration boundaries."""

from __future__ import annotations

from app.models.runtime import RuntimePolicyResult


SPENDING_KEYWORDS = {
    "spend",
    "spending",
    "expense",
    "expenses",
    "category",
    "merchant",
    "duplicate",
    "anomaly",
    "unusual",
    "消费",
    "支出",
    "花费",
    "类目",
    "商户",
    "重复",
    "异常",
}

BUDGET_KEYWORDS = {
    "budget",
    "saving",
    "savings",
    "cashflow",
    "cash flow",
    "plan",
    "预算",
    "储蓄",
    "存钱",
    "现金流",
    "计划",
}

MARKET_KEYWORDS = {
    "market",
    "macro",
    "economy",
    "stock",
    "fund",
    "news",
    "市场",
    "宏观",
    "经济",
    "股票",
    "基金",
    "新闻",
}

RISK_KEYWORDS = {
    "invest",
    "investment",
    "buy",
    "sell",
    "guarantee",
    "return",
    "收益",
    "投资",
    "买入",
    "卖出",
    "保证",
}


def _contains_any(message: str, keywords: set[str]) -> bool:
    lowered = message.lower()
    return any(keyword in lowered for keyword in keywords)


def evaluate_runtime_policy(
    user_message: str,
    transactions: list[dict] | None = None,
    monthly_totals: list[dict] | None = None,
) -> RuntimePolicyResult:
    specialists: list[str] = []
    has_spending_intent = _contains_any(user_message, SPENDING_KEYWORDS)
    has_budget_intent = _contains_any(user_message, BUDGET_KEYWORDS)
    has_market_intent = _contains_any(user_message, MARKET_KEYWORDS)
    has_risky_intent = _contains_any(user_message, RISK_KEYWORDS)
    has_data = bool(transactions or monthly_totals)

    if has_spending_intent:
        specialists.append("expense_analyst")
    if has_budget_intent:
        specialists.append("budget_analyst")

    risk_level = "high" if has_risky_intent else "medium" if has_market_intent else "low"
    audit_required = risk_level != "low" or bool(specialists) or not has_data

    if risk_level == "high" or len(specialists) >= 2 or len(user_message) > 160:
        complexity = "complex"
        max_tool_calls = 10
        max_deliberation_rounds = 1
    elif specialists:
        complexity = "moderate"
        max_tool_calls = 6
        max_deliberation_rounds = 1
    else:
        complexity = "simple"
        max_tool_calls = 3
        max_deliberation_rounds = 0

    return RuntimePolicyResult(
        complexity=complexity,
        risk_level=risk_level,
        required_specialists=specialists,
        audit_required=audit_required,
        allow_market_context=has_market_intent,
        max_tool_calls=max_tool_calls,
        max_deliberation_rounds=max_deliberation_rounds,
    )
