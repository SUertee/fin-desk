"""
LangChain DeepAgents factory for the finance team.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from deepagents import create_deep_agent
except Exception:
    create_deep_agent = None


CFO_SYSTEM_PROMPT = """You are the CFO agent for a personal finance operating system.

Your job:
- Coordinate the finance agent team.
- Use specialist subagents when the question needs expense analysis, budget coaching, audit review, or market context.
- Give concise answers in the user's language.
- Always separate conclusion, evidence, and actions.
- Do not present risky investment guidance as certainty.

Return a final answer that can be read directly by the user.
"""


def build_finance_subagents() -> list[dict[str, Any]]:
    return [
        {
            "name": "expense_analyst",
            "description": "Analyzes spending, category changes, anomalies, merchants, and duplicate-sensitive totals.",
            "system_prompt": "You are Expense Analyst. Return concise findings with specific evidence from the provided finance context. Focus on spending, categories, anomalies, and merchant concentration.",
        },
        {
            "name": "budget_coach",
            "description": "Turns finance context into budget limits, behavior interventions, reminders, and low-friction next actions.",
            "system_prompt": "You are Budget Coach. Return practical budget and behavior recommendations. Keep actions specific, low-friction, and tied to evidence.",
        },
        {
            "name": "auditor",
            "description": "Reviews finance answers for evidence quality, overconfidence, data limitations, and risky claims.",
            "system_prompt": "You are Auditor. Review claims for factual support, data limitations, and risk. Return confidence from 0 to 1 plus warnings.",
        },
        {
            "name": "market_scout",
            "description": "Provides lightweight market or macro context when relevant, with conservative risk framing.",
            "system_prompt": "You are Market Scout. Provide market context only when it is relevant. Avoid direct investment instructions. Always include limitations.",
        },
    ]


def extract_text_reply(result: dict[str, Any]) -> str:
    messages = result.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "assistant":
                content = message.get("content")
                if isinstance(content, str):
                    return content
            content = getattr(message, "content", None)
            if isinstance(content, str):
                return content

    output = result.get("output") or result.get("content")
    if isinstance(output, str):
        return output

    return ""


def _build_prompt(context: dict[str, Any]) -> str:
    payload = {
        "user_message": context["message"],
        "profile": context.get("profile", {}),
        "expense_snapshot": context.get("expense_snapshot", {}),
        "budget_snapshot": context.get("budget_snapshot", {}),
        "monthly_totals": context.get("monthly_totals", []),
        "transactions_sample": context.get("transactions_sample", []),
        "recent_chat_history": context.get("chat_history", []),
    }
    return (
        "Analyze this personal finance request. Use the finance team subagents when useful.\n"
        "After the narrative answer, include a compact JSON block with keys: "
        "summary_cards, findings, actions, audit.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


def _parse_embedded_data(reply: str) -> dict[str, Any] | None:
    start = reply.rfind("{")
    end = reply.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(reply[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def invoke_finance_deep_agent(context: dict[str, Any]) -> dict[str, Any]:
    if create_deep_agent is None:
        raise RuntimeError("deepagents package is not installed")

    model = os.getenv("DEEPAGENTS_MODEL") or os.getenv("OPENAI_MODEL") or "openai:gpt-4o-mini"
    agent = create_deep_agent(
        model=model,
        system_prompt=CFO_SYSTEM_PROMPT,
        subagents=build_finance_subagents(),
        name="finance-cfo",
    )
    result = await agent.ainvoke({"messages": [{"role": "user", "content": _build_prompt(context)}]})
    reply = extract_text_reply(result)
    return {
        "reply": reply,
        "agent_used": "cfo",
        "data": _parse_embedded_data(reply),
    }
