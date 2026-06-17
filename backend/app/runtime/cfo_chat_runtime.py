"""
Runtime boundary for the finance agent team.
"""

from __future__ import annotations

import logging
from typing import Any

from app.runtime.openai_cfo_runtime import OpenAICFORuntime
from app.runtime.runtime_policy import evaluate_runtime_policy
from app.runtime.trace_collector import TraceCollector
from app.tools.finance_tools import build_finance_context_payload
from app.tools.openai_finance_tools import OPENAI_FINANCE_TOOL_NAMES

logger = logging.getLogger(__name__)


class FinanceTeamRuntime:
    def __init__(self, openai_runtime: OpenAICFORuntime | None = None):
        self.openai_runtime = openai_runtime or OpenAICFORuntime()

    async def handle(
        self,
        user_id: str,
        message: str,
        profile: dict[str, Any],
        transactions: list[dict[str, Any]],
        monthly_totals: list[dict[str, Any]],
        chat_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        trace = TraceCollector.start_run(
            user_id=user_id,
            runtime_requested="openai",
        )
        policy = evaluate_runtime_policy(
            user_message=message,
            transactions=transactions,
            monthly_totals=monthly_totals,
        )
        trace.set_policy(policy.model_dump())
        trace.set_tools_available(OPENAI_FINANCE_TOOL_NAMES)
        try:
            context = self._build_context(
                user_id=user_id,
                message=message,
                profile=profile,
                transactions=transactions,
                monthly_totals=monthly_totals,
                chat_history=chat_history,
                policy=policy.model_dump(),
            )
            result = await self.openai_runtime.run(context)
            trace.mark_runtime_used("openai")
            self._log_trace(trace)
            return result
        except Exception as exc:
            trace.fail(exc)
            self._log_trace(trace)
            raise

    def _log_trace(self, trace: TraceCollector) -> None:
        logger.info("Finance runtime trace", extra={"trace": trace.to_log_dict()})

    def _build_context(
        self,
        *,
        user_id: str,
        message: str,
        profile: dict[str, Any],
        transactions: list[dict[str, Any]],
        monthly_totals: list[dict[str, Any]],
        chat_history: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        context = build_finance_context_payload(
            user_id=user_id,
            profile=profile,
            transactions=transactions,
            monthly_totals=monthly_totals,
            chat_history=chat_history,
        )
        context["message"] = message
        context["runtime_policy"] = policy
        return context
