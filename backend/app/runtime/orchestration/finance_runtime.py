"""Self-hosted CFO-first finance runtime."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.agents.specialists.contracts import SpecialistAgentOutput
from app.connectors.postgres.run_ledger_store import save_agent_run_record_db
from app.connectors.postgres.statement_import_store import list_latest_quality_reports_db
from app.models.agent_data import AgentAction, AgentAudit, AgentFinding, SummaryCard
from app.models.chat import ChatResponse
from app.models.runtime import RuntimePolicyResult
from app.runtime.contracts.output_validation import validate_output_contract
from app.runtime.execution import (
    AgentContext,
    AgentState,
    BoundedToolExecutor,
    HandoffRequest,
    HandoffResult,
    ToolObservation,
    ToolRegistry,
    ToolSpec,
    build_execution_plan,
)
from app.runtime.execution.artifact_registry import ArtifactRegistry
from app.runtime.execution.specialist_runner import SpecialistRunner
from app.runtime.memory.finance_memory_extractor import extract_finance_memory
from app.runtime.memory.session_context import write_session_context
from app.runtime.observability.trace_collector import TraceCollector
from app.runtime.orchestration.entry_router import EntryRouter
from app.runtime.orchestration.intake import ModelTurnContextualizer, TurnContextualizer
from app.runtime.orchestration.router import ModelIntentClassifier
from app.models.routing import route_for_path
from app.runtime.policy.audit_runner import should_run_audit
from app.runtime.policy.conversation_policy import compose_short_cfo_reply
from app.runtime.policy.cost_policy import estimate_run_cost
from app.runtime.policy.runtime_policy import evaluate_runtime_policy
from app.runtime.llm.deepseek_client import DeepSeekTextClient
from app.runtime.response.response_composer import compose_finance_chat_response
from app.tools.query_tools import extract_query_filters, run_transaction_query
from app.tools.finance_tools import (
    build_budget_snapshot,
    build_expense_snapshot,
    build_finance_context_payload,
)

logger = logging.getLogger(__name__)

SPECIALIST_TOOL_BY_AGENT = {
    "expense_analyst": "consult_expense_analyst",
    "budget_coach": "consult_budget_coach",
    "auditor": "consult_auditor",
    "market_context": "consult_market_context",
}


def _round_money(value: float | int | None) -> float:
    return round(float(value or 0), 2)


def _status_from_budget(status: str) -> str:
    if status == "good":
        return "good"
    if status == "risk":
        return "risk"
    if status == "watch":
        return "watch"
    return "neutral"


BUDGET_STATUS_ZH = {
    "good": "良好",
    "watch": "观察",
    "risk": "风险",
    "data_limited": "数据不足",
}


def _summary_cards(context: dict[str, Any]) -> list[SummaryCard]:
    expense = context.get("expense_snapshot", {})
    budget = context.get("budget_snapshot", {})
    zh = context.get("reply_language") == "zh"
    budget_status = str(budget.get("status") or "data_limited")
    return [
        SummaryCard(
            label="净现金流" if zh else "Net cash flow",
            value=f"{_round_money(expense.get('net_total')):,.2f}",
            status="good" if float(expense.get("net_total") or 0) >= 0 else "watch",
            note="已加载交易的收入减支出" if zh else "Income minus expenses from loaded transactions",
        ),
        SummaryCard(
            label="支出" if zh else "Expenses",
            value=f"{_round_money(expense.get('expense_total')):,.2f}",
            status="neutral",
            note=(
                f"{int(expense.get('transaction_count') or 0)} 笔有效交易"
                if zh
                else f"{int(expense.get('transaction_count') or 0)} active transactions"
            ),
        ),
        SummaryCard(
            label="预算状态" if zh else "Budget status",
            value=BUDGET_STATUS_ZH.get(budget_status, budget_status) if zh else budget_status,
            status=_status_from_budget(budget_status),
            note="支出与设定月收入之比" if zh else "Expense ratio against configured monthly income",
        ),
    ]



def _bounded_handoff_output(output: dict[str, Any]) -> dict[str, Any]:
    """Evidence-safe subset of a specialist output for the run ledger."""

    return {
        "specialist": output.get("specialist"),
        "findings": output.get("findings") or [],
        "recommendations": output.get("recommendations") or [],
        "limitations": output.get("limitations") or [],
    }


class FinanceRuntime:
    """Application runtime boundary for finance chat orchestration."""

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        specialist_runner: SpecialistRunner | None = None,
        llm_client: Any | None = None,
    ):
        self.tool_registry = tool_registry or self._build_tool_registry()
        self.specialist_runner = specialist_runner or SpecialistRunner()
        self.llm_client = llm_client if llm_client is not None else DeepSeekTextClient()
        # Client getter: nulling self.llm_client also disables classification.
        self.entry_router = EntryRouter(
            classifier=ModelIntentClassifier(lambda: self.llm_client)
        )
        self.turn_contextualizer = TurnContextualizer(
            model=ModelTurnContextualizer(lambda: self.llm_client)
        )

    async def handle(
        self,
        *,
        user_id: str,
        message: str,
        profile: dict[str, Any],
        transactions: list[dict[str, Any]],
        monthly_totals: list[dict[str, Any]],
        chat_history: list[dict[str, Any]],
        memory_context: dict[str, Any] | None = None,
        # CFO Room session scope for session memory; empty keeps the legacy
        # flat-history scope ("default").
        session_id: str = "",
        entrypoint: str = "chat",
        requested_specialist: str | None = None,
        on_reply_delta=None,
        on_pipeline_complete=None,
    ) -> dict[str, Any]:
        trace = TraceCollector.start_run(
            user_id=user_id,
            entrypoint=entrypoint,
            runtime_requested="self_hosted",
        )
        trace.set_model_name("self-hosted-deterministic")
        trace.set_output_contract("ChatResponse")

        try:
            # Intake: resolve follow-up references BEFORE routing. The raw
            # user text stays untouched for history/UI; everything the
            # runtime executes reads the effective message.
            turn = await self.turn_contextualizer.contextualize(
                message,
                chat_history=chat_history,
                memory_context=memory_context or {},
            )
            effective_message = turn.effective_message

            route_decision = await self.entry_router.decide(
                effective_message,
                chat_history=chat_history,
                memory_context=memory_context or {},
            )
            route = route_decision.route
            if route_decision.classifier_status != "skipped":
                trace.record_tool_call(
                    "route_classify",
                    status="called" if route_decision.classifier_status == "called" else "failed",
                    agent="cfo",
                    latency_ms=route_decision.classifier_latency_ms,
                )
            # An unresolved reference must never run a fabricated finance
            # query — ask for clarification instead.
            if turn.resolution_status == "needs_clarification" and route.run_finance_pipeline:
                route = route_for_path(
                    "clarification", "clarification", label="context_clarification"
                )
            if not route.run_finance_pipeline:
                response_payload = self._compose_non_analysis_response(
                    trace=trace,
                    route=route,
                    route_decision=route_decision,
                    turn=turn,
                    message=message,
                    profile=profile,
                    transactions=transactions,
                    monthly_totals=monthly_totals,
                    chat_history=chat_history,
                    memory_context=memory_context or {},
                )
                _, response_validation = validate_output_contract(
                    agent="cfo",
                    contract="ChatResponse",
                    model_type=ChatResponse,
                    payload=response_payload,
                )
                trace.record_output_validation(response_validation)
                if response_validation.status == "failed":
                    raise ValueError("FinanceRuntime returned invalid ChatResponse")
                trace.mark_runtime_used("self_hosted")
                self._finalize_trace(trace)
                self._log_trace(trace)
                self._persist_trace(trace)
                return response_payload

            policy = evaluate_runtime_policy(
                user_message=effective_message,
                transactions=transactions,
                monthly_totals=monthly_totals,
                requested_specialist=requested_specialist,
            )
            trace.set_policy(
                {
                    **policy.model_dump(),
                    "conversation_route": route.model_dump(mode="json"),
                    "route_decision": route_decision.ledger_dump(),
                    "contextualization": turn.ledger_dump(),
                }
            )
            context = AgentContext(
                request_id=trace.request_id,
                user_id=user_id,
                entrypoint=entrypoint,
                message=effective_message,
                raw_message=message,
                effective_message=effective_message,
                profile=profile,
                transactions=transactions,
                monthly_totals=monthly_totals,
                chat_history=chat_history,
                memory_context=memory_context or {},
                runtime_policy=policy.model_dump(),
            )
            state = AgentState()
            artifacts = ArtifactRegistry()
            plan = build_execution_plan(context, policy)
            state.selected_agents = plan.selected_agents
            trace.select_agents(plan.selected_agents)
            trace.set_tools_available(
                [
                    *[spec.name for spec in self.tool_registry.available()],
                    *SPECIALIST_TOOL_BY_AGENT.values(),
                ]
            )
            trace.set_input_summary(
                {
                    "message_length": len(message or ""),
                    "transaction_count": len(transactions),
                    "monthly_total_count": len(monthly_totals),
                    "chat_history_count": len(chat_history),
                    "memory_recent_turns_count": len(
                        context.memory_context.get("recent_turns") or []
                    ),
                    "memory_session_state_present": bool(
                        context.memory_context.get("session_memory")
                    ),
                    "memory_truncated": bool(context.memory_context.get("truncated")),
                    "memory_summary_used": bool(
                        context.memory_context.get("summary_used")
                    ),
                    "conversation_route": route.execution_path,
                }
            )

            executor = BoundedToolExecutor(
                self.tool_registry,
                allowed_tools=plan.tool_names,
                max_tool_calls=policy.max_tool_calls,
            )
            for step in plan.steps:
                if step.step_type != "tool":
                    continue
                observation = await executor.execute(
                    step.name,
                    {
                        "agent": step.agent,
                        "context": context,
                        "artifacts": artifacts.as_dict(),
                    },
                )
                state.record_tool_observation(observation)
                if observation.success:
                    artifacts.put(step.name, observation.result)
                trace.record_tool_call(
                    observation.tool_name,
                    status="called" if observation.success else "failed",
                    agent=observation.agent,
                    latency_ms=observation.latency_ms,
                )

            finance_context = artifacts.get("get_finance_context") or self._context_payload(context)
            reply_language = self._resolve_language(
                (profile or {}).get("preferences") or {}, message
            )
            finance_context = {**finance_context, "reply_language": reply_language}
            import_quality = artifacts.get("get_import_quality_report")
            if import_quality and import_quality.get("reports"):
                finance_context = {**finance_context, "import_quality": import_quality}
            query_result = artifacts.get("query_transactions")
            if query_result and query_result.get("count"):
                finance_context = {**finance_context, "transaction_query": query_result}
            specialist_outputs: dict[str, SpecialistAgentOutput] = {}
            for specialist in policy.required_specialists:
                request = HandoffRequest(
                    from_agent="cfo",
                    to_agent=specialist,
                    task=f"Produce {specialist} review for CFO response",
                    evidence=finance_context,
                    constraints=["Use loaded evidence only", "Call out limitations"],
                    output_contract="SpecialistAgentOutput",
                )
                result = self._run_specialist_handoff(request)
                state.record_handoff_result(result)
                trace.record_handoff(
                    from_agent=result.from_agent,
                    to_agent=result.to_agent,
                    status=result.status,
                    reason="typed_internal_handoff",
                    output=_bounded_handoff_output(result.output) if result.output else None,
                )
                trace.record_tool_call(
                    SPECIALIST_TOOL_BY_AGENT[specialist],
                    status="called" if result.status == "completed" else "failed",
                    agent="cfo",
                    latency_ms=result.latency_ms,
                )
                _, validation = validate_output_contract(
                    agent=specialist,
                    contract="SpecialistAgentOutput",
                    model_type=SpecialistAgentOutput,
                    payload=result.output,
                )
                trace.record_output_validation(validation)
                if validation.status == "passed":
                    specialist_outputs[specialist] = SpecialistAgentOutput.model_validate(
                        result.output
                    )

            if should_run_audit(policy, specialists_used=list(specialist_outputs)):
                audit_request = HandoffRequest(
                    from_agent="cfo",
                    to_agent="auditor",
                    task="Audit CFO and specialist evidence before final response",
                    evidence={
                        "finance_context": finance_context,
                        "specialists": {
                            key: value.model_dump()
                            for key, value in specialist_outputs.items()
                        },
                    },
                    constraints=["No investment/tax/legal advice", "Expose uncertainty"],
                    output_contract="SpecialistAgentOutput",
                )
                audit_result = self._run_specialist_handoff(audit_request, policy=policy)
                state.record_handoff_result(audit_result)
                trace.record_handoff(
                    from_agent=audit_result.from_agent,
                    to_agent=audit_result.to_agent,
                    status=audit_result.status,
                    reason="typed_internal_handoff",
                    output=_bounded_handoff_output(audit_result.output) if audit_result.output else None,
                )
                trace.record_tool_call(
                    SPECIALIST_TOOL_BY_AGENT["auditor"],
                    status="called" if audit_result.status == "completed" else "failed",
                    agent="cfo",
                    latency_ms=audit_result.latency_ms,
                )
                _, audit_validation = validate_output_contract(
                    agent="auditor",
                    contract="SpecialistAgentOutput",
                    model_type=SpecialistAgentOutput,
                    payload=audit_result.output,
                )
                trace.record_output_validation(audit_validation)
                if audit_validation.status == "passed":
                    specialist_outputs["auditor"] = SpecialistAgentOutput.model_validate(
                        audit_result.output
                    )

            response_payload = self._compose_response(
                context=finance_context,
                policy=policy,
                specialist_outputs=specialist_outputs,
            )
            response_payload["request_id"] = trace.request_id
            response_payload["route"] = route.model_dump(mode="json")
            if on_pipeline_complete is not None and route.emit_steps:
                from app.runtime.observability.steps_projection import project_steps

                await on_pipeline_complete(
                    project_steps(
                        {
                            "tool_calls": [tc.model_dump() for tc in trace.tool_calls],
                            "handoffs": [h.model_dump() for h in trace.handoffs],
                        }
                    )
                )
            await self._llm_compose_reply(
                trace=trace,
                context=finance_context,
                message=message,
                effective_message=effective_message,
                chat_history=chat_history,
                route=route,
                response_payload=response_payload,
                on_reply_delta=on_reply_delta,
            )
            _, response_validation = validate_output_contract(
                agent="cfo",
                contract="ChatResponse",
                model_type=ChatResponse,
                payload=response_payload,
            )
            trace.record_output_validation(response_validation)
            if response_validation.status == "failed":
                raise ValueError("FinanceRuntime returned invalid ChatResponse")

            audit = response_payload.get("data", {}).get("audit")
            if isinstance(audit, dict):
                trace.set_audit_status(audit.get("status"))
            self._write_memory(
                user_id=user_id,
                session_id=session_id,
                # Memory extraction (topic/capability/last_query) reads the
                # effective execution text, not the unresolved reference.
                message=effective_message,
                response_payload=response_payload,
                finance_context=finance_context,
                chat_history=chat_history,
            )
            trace.mark_runtime_used("self_hosted")
            self._finalize_trace(trace)
            self._log_trace(trace)
            self._persist_trace(trace)
            return response_payload
        except Exception as exc:
            trace.fail(exc)
            self._finalize_trace(trace)
            self._log_trace(trace)
            self._persist_trace(trace)
            raise

    def _compose_non_analysis_response(
        self,
        *,
        trace: TraceCollector,
        route,
        route_decision,
        turn,
        message: str,
        profile: dict[str, Any],
        transactions: list[dict[str, Any]],
        monthly_totals: list[dict[str, Any]],
        chat_history: list[dict[str, Any]],
        memory_context: dict[str, Any],
    ) -> dict[str, Any]:
        trace.set_policy(
            {
                "conversation_route": route.model_dump(mode="json"),
                "route_decision": route_decision.ledger_dump(),
                "contextualization": turn.ledger_dump(),
            }
        )
        trace.select_agents(["cfo"])
        trace.set_tools_available([])
        trace.set_input_summary(
            {
                "message_length": len(message or ""),
                "transaction_count": len(transactions),
                "monthly_total_count": len(monthly_totals),
                "chat_history_count": len(chat_history),
                "memory_recent_turns_count": len(memory_context.get("recent_turns") or []),
                "memory_session_state_present": bool(memory_context.get("session_memory")),
                "memory_truncated": bool(memory_context.get("truncated")),
                "memory_summary_used": bool(memory_context.get("summary_used")),
                "conversation_route": route.execution_path,
            }
        )
        return {
            "reply": compose_short_cfo_reply(
                route=route,
                message=message,
                profile=profile,
            ),
            "agent_used": "cfo",
            "request_id": trace.request_id,
            "data": None,
            "route": route.model_dump(mode="json"),
        }

    def _build_tool_registry(self) -> ToolRegistry:
        return ToolRegistry(
            [
                ToolSpec(
                    name="get_finance_context",
                    description="Build a complete finance context payload.",
                    executor=self._tool_finance_context,
                ),
                ToolSpec(
                    name="get_expense_snapshot",
                    description="Summarize transactions, categories, and anomalies.",
                    executor=self._tool_expense_snapshot,
                ),
                ToolSpec(
                    name="get_budget_snapshot",
                    description="Summarize income, expense ratio, and budget status.",
                    executor=self._tool_budget_snapshot,
                ),
                ToolSpec(
                    name="get_anomaly_summary",
                    description="Return anomaly summary from the expense snapshot.",
                    executor=self._tool_anomaly_summary,
                ),
                ToolSpec(
                    name="get_cashflow_summary",
                    description="Summarize monthly cash flow totals.",
                    executor=self._tool_cashflow_summary,
                ),
                ToolSpec(
                    name="get_import_quality_report",
                    description="Latest statement-import quality report per source.",
                    executor=self._tool_import_quality,
                ),
                ToolSpec(
                    name="query_transactions",
                    description="Typed ledger aggregation from extracted filters (nl2filters).",
                    executor=self._tool_query_transactions,
                ),
            ]
        )

    async def _tool_query_transactions(self, payload: dict[str, Any]) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        filters = extract_query_filters(context.message)
        result = run_transaction_query(context.user_id, filters)
        return ToolObservation(
            tool_name="query_transactions",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="typed_ledger_query",
            result=result,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def _tool_import_quality(self, payload: dict[str, Any]) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        reports = list_latest_quality_reports_db(context.user_id)
        return ToolObservation(
            tool_name="get_import_quality_report",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="data_quality_evidence",
            result={"reports": reports},
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    def _context_payload(self, context: AgentContext) -> dict[str, Any]:
        return build_finance_context_payload(
            user_id=context.user_id,
            profile=context.profile,
            transactions=context.transactions,
            monthly_totals=context.monthly_totals,
            chat_history=context.chat_history,
            memory_context=context.memory_context,
        ) | {
            "message": context.message,
            "runtime_policy": context.runtime_policy,
        }

    def _write_memory(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        response_payload: dict[str, Any],
        finance_context: dict[str, Any],
        chat_history: list[dict[str, Any]],
    ) -> None:
        memory = extract_finance_memory(
            user_message=message,
            response_payload=response_payload,
            finance_context=finance_context,
            chat_history=chat_history,
        )
        write_session_context(user_id=user_id, session_id=session_id, **memory)

    async def _tool_finance_context(self, payload: dict[str, Any]) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        result = self._context_payload(context)
        return ToolObservation(
            tool_name="get_finance_context",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="baseline_context",
            result=result,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def _tool_expense_snapshot(self, payload: dict[str, Any]) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        result = build_expense_snapshot(context.transactions, context.monthly_totals)
        return ToolObservation(
            tool_name="get_expense_snapshot",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="expense_evidence",
            result=result,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def _tool_budget_snapshot(self, payload: dict[str, Any]) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        result = build_budget_snapshot(
            context.profile,
            context.transactions,
            context.monthly_totals,
        )
        return ToolObservation(
            tool_name="get_budget_snapshot",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="budget_evidence",
            result=result,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def _tool_anomaly_summary(self, payload: dict[str, Any]) -> ToolObservation:
        started = perf_counter()
        artifacts = payload.get("artifacts") or {}
        snapshot = artifacts.get("get_expense_snapshot") or {}
        result = {
            "anomaly_count": snapshot.get("anomaly_count", 0),
            "anomalies": snapshot.get("anomalies", []),
        }
        return ToolObservation(
            tool_name="get_anomaly_summary",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="anomaly_evidence",
            result=result,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def _tool_cashflow_summary(self, payload: dict[str, Any]) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        net_total = sum(float(item.get("net") or 0) for item in context.monthly_totals)
        result = {
            "month_count": len(context.monthly_totals),
            "net_total": round(net_total, 2),
            "monthly_totals": context.monthly_totals,
        }
        return ToolObservation(
            tool_name="get_cashflow_summary",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="cashflow_evidence",
            result=result,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    def _run_specialist_handoff(
        self,
        request: HandoffRequest,
        *,
        policy: RuntimePolicyResult | None = None,
    ) -> HandoffResult:
        return self.specialist_runner.run(request, policy=policy)

    async def _llm_compose_reply(
        self,
        *,
        trace: TraceCollector,
        context: dict[str, Any],
        message: str,
        effective_message: str = "",
        chat_history: list[dict[str, Any]],
        route,
        response_payload: dict[str, Any],
        on_reply_delta=None,
    ) -> None:
        """Compose the final reply with the LLM when available.

        Grounded strictly in the run's evidence digest; on missing key or any
        provider failure the deterministic template reply stays — the user
        never sees an error from this step.
        """

        if not self.llm_client or not getattr(self.llm_client, "available", lambda *_: False)("chat"):
            trace.record_tool_call("llm_compose", status="skipped", agent="cfo")
            return
        started = perf_counter()
        try:
            digest = self._evidence_digest(context, response_payload)
            preferences = (context.get("profile") or {}).get("preferences") or {}
            language = self._resolve_language(preferences, message)
            tone = str(preferences.get("response_tone") or "balanced")
            system = (
                "You are the CFO of the user's personal finance workspace. "
                "Answer ONLY from the evidence digest — never invent numbers, "
                "dates, or merchants that are not present in it. If the "
                "evidence cannot answer the question, say so plainly. "
                "No investment, tax, or legal advice. "
                "Write plain conversational prose. Do NOT add pseudo-structure "
                "labels or headings such as 核心洞察/关键发现/总结/建议 — the "
                "product renders findings and actions separately from typed data. "
                + ("Reply in Chinese. " if language == "zh" else "Reply in English. ")
                + {
                    "concise": "Keep it to 1-2 sentences.",
                    "comprehensive": "Explain thoroughly with the key figures.",
                }.get(tone, "Keep it focused: lead with the answer, then one insight.")
            )
            if getattr(route, "execution_path", "") == "cfo_followup":
                system += (
                    "Answer the current follow-up directly; do not restate the full "
                    "finance brief unless it is necessary for the answer. "
                )
            recent = "\n".join(
                f"{turn.get('role')}: {str(turn.get('content'))[:200]}"
                for turn in (chat_history or [])[-6:]
            )
            # Raw text keeps the user's phrasing; the contextualized reading
            # tells the composer what the evidence actually answers.
            interpreted = (
                f"Interpreted as: {effective_message}\n\n"
                if effective_message and effective_message != message
                else ""
            )
            prompt = (
                f"User message: {message}\n\n"
                + interpreted
                + f"Evidence digest:\n{digest}\n\n"
                + (f"Recent conversation:\n{recent}\n\n" if recent else "")
                + "Compose the CFO reply."
            )
            if on_reply_delta is not None and hasattr(self.llm_client, "generate_text_stream"):
                result = await self.llm_client.generate_text_stream(
                    prompt, profile="chat", system=system, on_delta=on_reply_delta
                )
            else:
                result = await self.llm_client.generate_text(prompt, profile="chat", system=system)
            if result.content:
                response_payload["reply"] = result.content
                trace.set_usage(result.usage)
                trace.set_model_name(result.model_name or "deepseek-chat")
                trace.record_tool_call(
                    "llm_compose",
                    status="called",
                    agent="cfo",
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                )
        except Exception as exc:
            logger.warning("LLM compose failed; deterministic reply kept: %s", exc)
            trace.record_tool_call(
                "llm_compose",
                status="failed",
                agent="cfo",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

    @staticmethod
    def _evidence_digest(
        context: dict[str, Any], response_payload: dict[str, Any]
    ) -> str:
        import json as _json

        expense = context.get("expense_snapshot", {})
        budget = context.get("budget_snapshot", {})
        data = response_payload.get("data") or {}
        digest = {
            "typed_query_result": context.get("transaction_query"),
            "expense_snapshot": {
                "expense_total": expense.get("expense_total"),
                "income_total": expense.get("income_total"),
                "net_total": expense.get("net_total"),
                "transaction_count": expense.get("transaction_count"),
                "top_categories": (expense.get("top_categories") or [])[:5],
                "anomaly_count": len(expense.get("anomalies") or []),
            },
            "budget_snapshot": budget,
            "findings": data.get("findings"),
            "actions": data.get("actions"),
            "audit": data.get("audit"),
            "import_quality_warnings": [
                warning
                for report in (context.get("import_quality") or {}).get("reports", [])
                for warning in report.get("warnings", [])
            ][:3],
        }
        return _json.dumps(digest, ensure_ascii=False, default=str)

    def _compose_response(
        self,
        *,
        context: dict[str, Any],
        policy: RuntimePolicyResult,
        specialist_outputs: dict[str, SpecialistAgentOutput],
    ) -> dict[str, Any]:
        expense = context.get("expense_snapshot", {})
        budget = context.get("budget_snapshot", {})
        findings: list[AgentFinding] = []
        actions: list[AgentAction] = []
        warnings: list[str] = []

        for specialist, output in specialist_outputs.items():
            if specialist == "auditor":
                warnings.extend(output.limitations)
                warnings.extend(
                    evidence
                    for finding in output.findings
                    for evidence in finding.evidence
                    if finding.risk_level != "low"
                )
                continue
            findings.extend(
                AgentFinding(
                    agent=specialist,
                    title=finding.title,
                    evidence=finding.evidence,
                )
                for finding in output.findings
            )
            actions.extend(
                AgentAction(
                    title=recommendation.title,
                    rationale=recommendation.rationale,
                    effort="medium",
                    impact="high" if policy.risk_level == "high" else "medium",
                )
                for recommendation in output.recommendations
            )

        if not findings and expense.get("transaction_count"):
            findings.append(
                AgentFinding(
                    agent="cfo",
                    title="Loaded transaction context is available",
                    evidence=[
                        f"{expense.get('transaction_count')} transactions; net cash flow {expense.get('net_total')}."
                    ],
                )
            )

        audit_output = specialist_outputs.get("auditor")
        audit_status = "needs_review" if policy.audit_required or warnings else "verified"
        if not context.get("transactions_sample"):
            audit_status = "data_limited"
        audit = AgentAudit(
            confidence=audit_output.confidence if audit_output else 0.68,
            status=audit_status,
            warnings=warnings[:5],
        )

        query = context.get("transaction_query")
        preferences = (context.get("profile") or {}).get("preferences") or {}
        language = self._resolve_language(preferences, context.get("message") or "")
        tone = str(preferences.get("response_tone") or "balanced")
        evidence_level = str(preferences.get("evidence_level") or "detailed")

        budget_status = budget.get("status") or "data_limited"
        budget_status_zh = {
            "good": "良好",
            "watch": "观察",
            "risk": "风险",
            "data_limited": "数据不足",
        }.get(budget_status, budget_status)
        net_total = _round_money(expense.get("net_total"))
        expense_total = _round_money(expense.get("expense_total"))

        query_line = ""
        if query:
            query_filters = query.get("filters") or {}
            scope_parts = []
            if query_filters.get("date_from"):
                scope_parts.append(f"{query_filters['date_from']} ~ {query_filters.get('date_to', '')}")
            if query_filters.get("category"):
                category_zh = {
                    "dining": "餐饮", "transport": "交通", "shopping": "购物",
                    "groceries": "买菜", "housing": "住房", "entertainment": "娱乐",
                    "travel": "旅行", "utilities": "水电", "services": "订阅服务",
                    "health": "医疗", "transfer": "转账", "education": "教育",
                }
                label = str(query_filters["category"])
                scope_parts.append(category_zh.get(label, label) if language == "zh" else label)
            scope = " ".join(scope_parts)
            if language == "zh":
                kind = "收入" if query_filters.get("direction") == "income" else "支出"
                query_line = f"{scope}{kind}合计 {query['total']:,.2f}（{query['count']} 笔）。"
            else:
                kind = "income" if query_filters.get("direction") == "income" else "spend"
                query_line = f"{scope} {kind} totals {query['total']:,.2f} across {query['count']} transactions. "

        if query_line:
            # The typed query answered the question; skip the generic summary.
            reply = query_line
            if actions and language == "zh":
                reply += f"另外，最高优先级建议：{actions[0].title}。"
            elif actions:
                reply += f"Also worth noting: {actions[0].title}."
        elif language == "zh":
            reply = (
                "我以 CFO 优先流程复核了你已加载的财务数据。"
                f"当前净现金流 {net_total:,.2f}，支出合计 {expense_total:,.2f}，"
                f"预算状态为{budget_status_zh}。"
            )
            if actions:
                reply += f"最高优先级：{actions[0].title}。"
            elif not context.get("transactions_sample"):
                reply += "建议先导入交易或账单数据，再依赖详细建议。"
            else:
                reply += "请持续关注最大的支出类目，并在新交易后刷新数据。"
        else:
            reply = (
                "I reviewed your loaded finance context with a CFO-first flow. "
                f"Current net cash flow is {net_total:,.2f}, "
                f"expense total is {expense_total:,.2f}, "
                f"and budget status is {budget_status}. "
            )
            if actions:
                reply += f"Highest priority: {actions[0].title}."
            elif not context.get("transactions_sample"):
                reply += "Add transactions or statement data before relying on detailed recommendations."
            else:
                reply += "Keep monitoring the largest categories and refresh the data after new transactions."

        if tone == "concise":
            # First sentences only: headline numbers plus the top action.
            reply = reply.split("。")[0] + "。" if language == "zh" else reply.split(". ")[0] + "."
            if actions:
                top = f"最高优先级：{actions[0].title}。" if language == "zh" else f" Top action: {actions[0].title}."
                reply += top
        elif tone == "comprehensive":
            extra = (
                f"共 {len(findings)} 条发现、{len(actions)} 条建议；审计状态 {audit.status}。"
                if language == "zh"
                else f" In total: {len(findings)} findings and {len(actions)} actions; audit status {audit.status}."
            )
            reply += extra

        if evidence_level == "brief":
            findings = [
                finding.model_copy(update={"evidence": finding.evidence[:1]})
                for finding in findings
            ]
            audit = audit.model_copy(update={"warnings": audit.warnings[:2]})
        elif evidence_level == "audit_heavy":
            audit_note = (
                f"审计置信度 {audit.confidence:.2f}，警告 {len(audit.warnings)} 条。"
                if language == "zh"
                else f" Audit confidence {audit.confidence:.2f} with {len(audit.warnings)} warnings."
            )
            reply += audit_note

        return compose_finance_chat_response(
            reply=reply,
            summary_cards=_summary_cards(context),
            findings=findings,
            actions=actions,
            audit=audit,
        )

    @staticmethod
    def _resolve_language(preferences: dict[str, Any], message: str) -> str:
        preferred = str(preferences.get("preferred_language") or "auto")
        if preferred in ("zh", "en"):
            return preferred
        return "zh" if any("一" <= ch <= "鿿" for ch in message) else "en"

    def _finalize_trace(self, trace: TraceCollector) -> None:
        trace.set_cost(
            estimate_run_cost(
                entrypoint=trace.entrypoint,
                usage=trace.usage,
                model_name=trace.model_name,
            )
        )

    def _log_trace(self, trace: TraceCollector) -> None:
        logger.info("Finance runtime trace", extra={"trace": trace.to_log_dict()})

    def _persist_trace(self, trace: TraceCollector) -> None:
        saved = save_agent_run_record_db(trace.to_run_record())
        if not saved:
            logger.debug("Agent run record was not persisted request_id=%s", trace.request_id)
