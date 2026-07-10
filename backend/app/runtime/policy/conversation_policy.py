"""Conversation-level reply policy for non-analysis routes."""

from __future__ import annotations

from typing import Any

from app.models.routing import ConversationRoute


def compose_short_cfo_reply(
    *,
    route: ConversationRoute,
    message: str,
    profile: dict[str, Any] | None = None,
) -> str:
    """Return a compact CFO reply without invoking the finance pipeline."""

    preferences = (profile or {}).get("preferences") or {}
    language = str(preferences.get("preferred_language") or "auto")
    zh = language == "zh" or (
        language == "auto" and any("一" <= ch <= "鿿" for ch in message)
    )

    if route.execution_path == "evidence_only":
        return (
            "可以。点开上一条回答下方的“引用来源”，就能看到这次结论用到的"
            "证据来源、团队发现和数据覆盖。"
            if zh
            else "Sure. Click \"引用来源\" under the previous CFO answer to see the sources, specialist findings, and data coverage behind it."
        )

    if route.execution_path == "clarification":
        return (
            "你想让我看哪一块财务问题？可以直接问支出、预算、现金流、重复交易或某一天的账单。"
            if zh
            else "Which finance area should I review? You can ask about spending, budget, cash flow, duplicates, or a specific statement day."
        )

    if route.intent == "acknowledgement":
        return (
            "收到。你可以继续问我某个支出、预算目标或账单异常。"
            if zh
            else "Got it. You can ask me about a spending category, budget goal, or statement anomaly."
        )

    return (
        "我在。你可以直接问我这个月的钱花在哪、哪类支出异常，或者让 CFO 做一次健康检查。"
        if zh
        else "I'm here. Ask where this month's money went, which spending looks unusual, or request a CFO health check."
    )
