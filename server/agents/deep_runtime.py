"""
Runtime boundary for the finance agent team.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from agents.finance_tools import build_finance_context_payload
from models.agent_data import normalize_finance_agent_data

logger = logging.getLogger(__name__)


class FinanceTeamRuntime:
    def __init__(self, langgraph_runner: Any):
        self.langgraph_runner = langgraph_runner

    async def handle(
        self,
        user_id: str,
        message: str,
        profile: dict[str, Any],
        transactions: list[dict[str, Any]],
        monthly_totals: list[dict[str, Any]],
        chat_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        context = build_finance_context_payload(
            user_id=user_id,
            profile=profile,
            transactions=transactions,
            monthly_totals=monthly_totals,
            chat_history=chat_history,
        )
        context["message"] = message

        runtime = os.getenv("FINANCE_AGENT_RUNTIME", "langgraph").lower()
        if runtime == "deepagents":
            try:
                return await self._invoke_deepagents(context)
            except Exception:
                logger.exception("DeepAgents runtime failed; falling back to LangGraph")

        return await self._invoke_langgraph(
            user_id=user_id,
            message=message,
            profile=profile,
            transactions=transactions,
            monthly_totals=monthly_totals,
            chat_history=chat_history,
        )

    async def _invoke_deepagents(self, context: dict[str, Any]) -> dict[str, Any]:
        from agents.deep_agent_factory import invoke_finance_deep_agent

        result = await invoke_finance_deep_agent(context)
        data = normalize_finance_agent_data(result.get("data"))
        return {
            "reply": result.get("reply") or "I could not produce a finance summary.",
            "agent_used": result.get("agent_used") or "cfo",
            "data": data,
        }

    async def _invoke_langgraph(
        self,
        user_id: str,
        message: str,
        profile: dict[str, Any],
        transactions: list[dict[str, Any]],
        monthly_totals: list[dict[str, Any]],
        chat_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        state = {
            "user_id": user_id,
            "message": message,
            "profile": profile,
            "transactions": transactions,
            "monthly_totals": monthly_totals,
            "chat_history": chat_history,
            "routed_agent": "",
            "refined_query": "",
            "agent_reply": "",
            "agent_data": None,
            "needs_advisor_review": False,
            "advisor_comment": "",
            "final_reply": "",
            "agent_used": "",
        }
        result = await self.langgraph_runner.ainvoke(state)
        data = normalize_finance_agent_data(result.get("agent_data"))
        return {
            "reply": result.get("final_reply") or result.get("agent_reply") or "",
            "agent_used": result.get("agent_used") or "general",
            "data": data,
        }
