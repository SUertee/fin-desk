"""Inbound gateway from external agents into the finance runtime."""

from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from app.connectors.postgres.transactions_store import (
    get_latest_analysis_run_db,
    list_transactions_db,
)
from app.gateways.agent_gateway.agent_profile import FINANCE_AGENT_ID
from app.gateways.agent_gateway.task_contracts import (
    AgentTaskRequest,
    AgentTaskResponse,
)
from app.gateways.agent_gateway.task_store import AgentTaskStore
from app.runtime.memory import build_memory_context
from app.runtime.orchestration.finance_runtime import FinanceRuntime
from app.services.memory import get_chat_history
from app.services.user_store import get_profile


ProfileLoader = Callable[[str], Any]
TransactionsLoader = Callable[[str, int], list[dict[str, Any]]]
AnalysisRunLoader = Callable[[str], dict[str, Any] | None]
ChatHistoryLoader = Callable[[str], list[dict[str, Any]]]


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}


def _task_message(req: AgentTaskRequest) -> str:
    prefix = f"External agent task: {req.capability}."
    requester = f" Requester: {req.requester_agent}." if req.requester_agent else ""
    context = f" Context: {req.context}." if req.context else ""
    return f"{prefix}{requester} {req.message}{context}".strip()


class InboundAgentGateway:
    """Translates external agent tasks into the internal FinanceRuntime."""

    def __init__(
        self,
        *,
        runtime: FinanceRuntime | None = None,
        task_store: AgentTaskStore | None = None,
        profile_loader: ProfileLoader = get_profile,
        transactions_loader: TransactionsLoader = list_transactions_db,
        analysis_run_loader: AnalysisRunLoader = get_latest_analysis_run_db,
        chat_history_loader: ChatHistoryLoader = get_chat_history,
    ) -> None:
        self.runtime = runtime or FinanceRuntime()
        self.task_store = task_store or AgentTaskStore()
        self.profile_loader = profile_loader
        self.transactions_loader = transactions_loader
        self.analysis_run_loader = analysis_run_loader
        self.chat_history_loader = chat_history_loader

    async def submit_task(self, req: AgentTaskRequest) -> AgentTaskResponse:
        task_id = req.task_id or f"finance-task-{uuid4().hex}"
        try:
            profile = _model_dump(self.profile_loader(req.user_id))
            transactions = self.transactions_loader(req.user_id, 200)
            run = self.analysis_run_loader(req.user_id)
            monthly_totals = run.get("monthly_totals", []) if run else []
            chat_history = self.chat_history_loader(req.user_id)
            memory_context = build_memory_context(
                user_id=req.user_id,
                chat_history=chat_history,
            )

            result = await self.runtime.handle(
                user_id=req.user_id,
                message=_task_message(req),
                profile=profile,
                transactions=transactions,
                monthly_totals=monthly_totals,
                chat_history=chat_history,
                memory_context=memory_context.model_dump(),
            )
            response = AgentTaskResponse(
                ok=True,
                task_id=task_id,
                status="completed",
                agent_id=FINANCE_AGENT_ID,
                capability=req.capability,
                requester_agent=req.requester_agent,
                correlation_id=req.correlation_id,
                reply=str(result.get("reply") or ""),
                artifacts={
                    "finance_response": result,
                    "runtime": "self_hosted",
                },
            )
        except Exception as exc:
            response = AgentTaskResponse(
                ok=False,
                task_id=task_id,
                status="failed",
                agent_id=FINANCE_AGENT_ID,
                capability=req.capability,
                requester_agent=req.requester_agent,
                correlation_id=req.correlation_id,
                error=str(exc),
            )
        return self.task_store.save(response)

    def get_task(self, task_id: str) -> AgentTaskResponse | None:
        return self.task_store.get(task_id)
