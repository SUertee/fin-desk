"""Self-hosted CFO-first finance runtime."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from time import perf_counter
from typing import Any

from app.agents.specialists.contracts import SpecialistAgentOutput
from app.connectors.postgres.run_ledger_store import save_agent_run_record_db
from app.connectors.postgres.exchange_rate_store import get_exchange_rate_snapshot_db
from app.connectors.postgres.statement_import_store import list_latest_quality_reports_db
from app.models.agent_data import AgentAction, AgentAudit, AgentFinding, SummaryCard
from app.models.chat import ChatResponse
from app.models.external_market_data import ExternalMarketHistoryArtifact
from app.models.runtime import AgentRunUsage, RuntimePolicyResult
from app.runtime.capabilities import (
    CapabilityCatalog,
    CapabilityHealthService,
    CapabilityResolver,
    bind_execution_plan,
    get_capability_health_service,
)
from app.runtime.capabilities.contracts import CapabilityRuntimeStatus
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
from app.runtime.policy.runtime_policy import evaluate_runtime_policy
from app.runtime.costing import CostingService
from app.config.settings import get_settings
from app.runtime.llm.deepseek_client import DeepSeekTextClient
from app.runtime.response.response_composer import compose_finance_chat_response
from app.services.investment_research_runtime import get_investment_research_service
from app.services.web_research import WebResearchService, build_web_research_service
from app.tools.investment_research_tools import (
    extract_instrument_reference,
    project_instrument_research,
)
from app.tools.web_research import WebResearchTool
from app.tools.mcp_market_data import (
    VibeMarketDataTool,
    build_vibe_market_data_tool,
    has_external_market_data_intent,
    project_external_history_for_specialist,
)
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
    "investment_research": "consult_investment_research",
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


def _response_summary_cards(context: dict[str, Any]) -> list[SummaryCard]:
    research = context.get("investment_research") or {}
    status = research.get("status")
    if status in {"symbol_required", "unavailable"}:
        return []
    if status != "available":
        return _summary_cards(context)

    zh = context.get("reply_language") == "zh"
    quote = research.get("quote") or {}
    price = quote.get("price") or {}
    history = research.get("history") or {}
    evidence = research.get("evidence") or []
    quote_value = price.get("amount")
    quote_currency = str(price.get("currency") or "")
    change = history.get("change_percent")
    return [
        SummaryCard(
            label="最近行情" if zh else "Latest quote",
            value=(
                f"{quote_currency} {quote_value}"
                if quote_value is not None
                else ("暂无" if zh else "Unavailable")
            ),
            status="neutral",
            note=(
                f"来源 {quote.get('source')}; 截至 {quote.get('quote_as_of')}"
                if zh
                else f"Source {quote.get('source')}; as of {quote.get('quote_as_of')}"
            ),
        ),
        SummaryCard(
            label="观察期变化" if zh else "Observed change",
            value=f"{change}%" if change is not None else ("暂无" if zh else "Unavailable"),
            status="watch" if change is not None else "neutral",
            note=(
                f"{history.get('date_from')} 至 {history.get('date_to')}"
                if zh
                else f"{history.get('date_from')} to {history.get('date_to')}"
            ),
        ),
        SummaryCard(
            label="证据来源" if zh else "Evidence sources",
            value=str(len(evidence)),
            status="good" if evidence else "watch",
            note=(
                "只读研究，不执行交易"
                if zh
                else "Read-only research; no trade execution"
            ),
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
        costing_service: CostingService | None = None,
        web_research_service: WebResearchService | None = None,
        web_research_tool: WebResearchTool | None = None,
        mcp_market_data_tool: VibeMarketDataTool | None = None,
        capability_health_service: CapabilityHealthService | None = None,
        granted_capabilities: set[str] | None = None,
    ):
        self.web_research_tool = web_research_tool or WebResearchTool(
            web_research_service or build_web_research_service()
        )
        mcp_settings = get_settings().mcp
        injected_mcp_tool = mcp_market_data_tool is not None
        self.mcp_market_data_tool = mcp_market_data_tool
        if self.mcp_market_data_tool is None and mcp_settings.enabled:
            self.mcp_market_data_tool = build_vibe_market_data_tool(mcp_settings)
        self.capability_health_service = capability_health_service
        if (
            self.capability_health_service is None
            and self.mcp_market_data_tool is not None
            and not injected_mcp_tool
        ):
            self.capability_health_service = get_capability_health_service()
        self.tool_registry = tool_registry or self._build_tool_registry()
        self.specialist_runner = specialist_runner or SpecialistRunner()
        optional_statuses = None
        if self.mcp_market_data_tool is None and not injected_mcp_tool:
            optional_statuses = {
                "get_vibe_market_data": CapabilityRuntimeStatus(
                    enabled=False,
                    available=False,
                    reason="Disabled by configuration",
                )
            }
        self.capability_catalog = CapabilityCatalog.from_registries(
            self.tool_registry,
            self.specialist_runner.registry,
            optional_tool_statuses=optional_statuses,
        )
        self.capability_resolver = CapabilityResolver(self.capability_catalog)
        self.available_capabilities = frozenset(
            item.descriptor.capability_id
            for item in self.capability_catalog.list()
            if item.status.enabled and item.status.available
        )
        self.granted_capabilities = frozenset(
            granted_capabilities
            if granted_capabilities is not None
            else self.available_capabilities
        )
        self.llm_client = llm_client if llm_client is not None else DeepSeekTextClient()
        self.costing_service = costing_service or CostingService(
            exchange_rate_lookup=get_exchange_rate_snapshot_db
        )
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
            llm_stages: dict[str, dict[str, Any]] = {}
            intake = await self.turn_contextualizer.contextualize_with_trace(
                message,
                chat_history=chat_history,
                memory_context=memory_context or {},
            )
            turn = intake.turn
            effective_message = turn.effective_message
            contextualization_record = self._contextualization_record(intake, message)
            # Account for the real LLM call only — a deterministic resolve
            # must never fabricate one.
            if intake.model_status in ("called", "failed", "invalid_output"):
                trace.record_tool_call(
                    "turn_contextualize",
                    status="called" if intake.model_status == "called" else "failed",
                    agent="cfo",
                    latency_ms=intake.model_latency_ms,
                )
                trace.add_usage(intake.model_usage)
                llm_stages["turn_contextualize"] = self._llm_stage_entry(
                    trace,
                    status=intake.model_status,
                    usage=intake.model_usage,
                    model_name=intake.model_name,
                    profile="router",
                    latency_ms=intake.model_latency_ms,
                )

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
                trace.add_usage(route_decision.classifier_usage)
                llm_stages["route_classify"] = self._llm_stage_entry(
                    trace,
                    status=route_decision.classifier_status,
                    usage=route_decision.classifier_usage,
                    model_name=route_decision.classifier_model,
                    profile="router",
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
                    contextualization_record=contextualization_record,
                    message=message,
                    profile=profile,
                    transactions=transactions,
                    monthly_totals=monthly_totals,
                    chat_history=chat_history,
                    memory_context=memory_context or {},
                )
                if llm_stages:
                    trace.policy["llm_usage_by_stage"] = llm_stages
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
                self._finalize_trace(trace, profile)
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
                    "contextualization": contextualization_record,
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
            available_capabilities = set(
                self.available_capabilities & self.granted_capabilities
            )
            if (
                has_external_market_data_intent(effective_message)
                and self.capability_health_service is not None
            ):
                mcp_status = (
                    await self.capability_health_service.vibe_market_data_status()
                )
                if not mcp_status.available:
                    available_capabilities.discard(
                        "investment.external_market_history"
                    )
            plan = build_execution_plan(
                context,
                policy,
                available_capabilities=available_capabilities,
            )
            bound_plan = bind_execution_plan(
                plan,
                self.capability_resolver,
                granted_capabilities=self.granted_capabilities,
            )
            web_research_budget = (
                self.web_research_tool.new_budget()
                if "search_web_research" in bound_plan.tool_names
                else None
            )
            state.selected_agents = list(bound_plan.selected_agents)
            trace.select_agents(list(bound_plan.selected_agents))
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
                allowed_tools=bound_plan.tool_names,
                max_tool_calls=policy.max_tool_calls,
            )
            for step in bound_plan.steps:
                if step.step_type != "tool":
                    continue
                observation = await executor.execute(
                    step.registry_name,
                    {
                        "agent": step.agent,
                        "context": context,
                        "artifacts": artifacts.as_dict(),
                        "web_research_budget": web_research_budget,
                    },
                )
                state.record_tool_observation(observation)
                if observation.success:
                    artifacts.put(step.registry_name, observation.result)
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
            investment_research = artifacts.get("get_investment_research_context")
            if investment_research:
                finance_context = {
                    **finance_context,
                    "investment_research": investment_research,
                }
            external_market_history = artifacts.get("get_vibe_market_data")
            if external_market_history:
                artifact = ExternalMarketHistoryArtifact.model_validate(
                    external_market_history
                )
                finance_context = {
                    **finance_context,
                    "external_market_history": external_market_history,
                    "investment_research": project_external_history_for_specialist(
                        artifact
                    ),
                }
            elif has_external_market_data_intent(context.message):
                finance_context = {
                    **finance_context,
                    "investment_research": {
                        "status": "unavailable",
                        "reason": "The requested external MCP market-data capability is disabled or unavailable.",
                        "trade_actions_allowed": False,
                    },
                }
            web_research = artifacts.get("search_web_research")
            if web_research:
                finance_context = {**finance_context, "web_research": web_research}
            specialist_outputs: dict[str, SpecialistAgentOutput] = {}
            handoff_names = bound_plan.handoff_names
            for specialist in [name for name in handoff_names if name != "auditor"]:
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

            if "auditor" in handoff_names and should_run_audit(
                policy, specialists_used=list(specialist_outputs)
            ):
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
            compose_stage = await self._llm_compose_reply(
                trace=trace,
                context=finance_context,
                message=message,
                effective_message=effective_message,
                chat_history=chat_history,
                route=route,
                response_payload=response_payload,
                on_reply_delta=on_reply_delta,
            )
            if compose_stage is not None:
                llm_stages["llm_compose"] = compose_stage
            if llm_stages:
                trace.policy["llm_usage_by_stage"] = llm_stages
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
            self._finalize_trace(trace, profile)
            self._log_trace(trace)
            self._persist_trace(trace)
            return response_payload
        except Exception as exc:
            trace.fail(exc)
            self._finalize_trace(trace, profile)
            self._log_trace(trace)
            self._persist_trace(trace)
            raise

    def _compose_non_analysis_response(
        self,
        *,
        trace: TraceCollector,
        route,
        route_decision,
        contextualization_record: dict[str, Any],
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
                "contextualization": contextualization_record,
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

    def _llm_stage_entry(
        self,
        trace: TraceCollector,
        *,
        status: str,
        usage,
        model_name: str | None,
        profile: str,
        latency_ms: float | None,
    ) -> dict[str, Any]:
        """Bounded per-stage LLM accounting for policy.llm_usage_by_stage.

        Metadata only — tokens, model, profile, status.
        Never prompts, chat history, or ledger payloads. Usage is included
        whenever the provider reported one, even for invalid output: those
        tokens were billed.
        """

        entry: dict[str, Any] = {
            "status": status,
            "latency_ms": latency_ms,
            "model_name": model_name,
            "profile": profile,
        }
        if usage is not None:
            parsed = AgentRunUsage.model_validate(usage)
            entry.update(
                request_count=parsed.request_count,
                model_response_count=parsed.model_response_count,
                input_tokens=parsed.input_tokens,
                cached_input_tokens=parsed.cached_input_tokens,
                uncached_input_tokens=parsed.uncached_input_tokens,
                output_tokens=parsed.output_tokens,
                total_tokens=parsed.total_tokens,
            )
        return entry

    @staticmethod
    def _contextualization_record(intake, raw_message: str) -> dict[str, Any]:
        """Developer-layer intake projection for the run ledger.

        Bounded by construction: message excerpts only — never the full
        chat history, prompts, or raw ledger payloads.
        """

        from app.runtime.orchestration.router.facts import excerpt

        turn = intake.turn
        return {
            "stage": "turn_contextualization",
            "raw_message_excerpt": excerpt(raw_message),
            "effective_message_excerpt": (
                excerpt(turn.effective_message) if turn.rewrite_applied else ""
            ),
            **turn.ledger_dump(),
            "model": {
                "status": intake.model_status,
                "latency_ms": intake.model_latency_ms,
                "model_name": intake.model_name,
                "profile": "router",
            },
        }

    def _build_tool_registry(self) -> ToolRegistry:
        specs = [
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
            ToolSpec(
                name="get_investment_research_context",
                description="Fetch bounded, sourced stock or ETF research evidence.",
                executor=self._tool_investment_research_context,
                owner="investment_research",
            ),
            self.web_research_tool.spec(),
        ]
        if self.mcp_market_data_tool is not None:
            specs.append(self.mcp_market_data_tool.spec())
        return ToolRegistry(specs)

    async def _tool_investment_research_context(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        reference = extract_instrument_reference(context.message)
        if reference is None:
            result = {
                "status": "symbol_required",
                "reason": "An explicit stock or ETF symbol is required; company names are not inferred.",
                "trade_actions_allowed": False,
            }
            return ToolObservation(
                tool_name="get_investment_research_context",
                success=True,
                agent=str(payload.get("agent") or "cfo"),
                purpose="sourced_investment_research",
                result=result,
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

        symbol, asset_type = reference
        date_to = date.today()
        try:
            snapshot = get_investment_research_service().get_instrument_research(
                context.user_id,
                symbol,
                asset_type=asset_type,
                date_from=date_to - timedelta(days=90),
                date_to=date_to,
            )
            result = project_instrument_research(snapshot)
        except Exception as exc:
            logger.warning(
                "Investment research unavailable symbol=%s error=%s",
                symbol,
                type(exc).__name__,
            )
            result = {
                "status": "unavailable",
                "symbol": symbol,
                "asset_type": asset_type,
                "reason": "Sourced market evidence is currently unavailable.",
                "trade_actions_allowed": False,
            }
        return ToolObservation(
            tool_name="get_investment_research_context",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="sourced_investment_research",
            result=result,
            latency_ms=round((perf_counter() - started) * 1000, 2),
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
    ) -> dict[str, Any] | None:
        """Compose the final reply with the LLM when available.

        Grounded strictly in the run's evidence digest; on missing key or any
        provider failure the deterministic template reply stays — the user
        never sees an error from this step.
        """

        if not self.llm_client or not getattr(self.llm_client, "available", lambda *_: False)("chat"):
            trace.record_tool_call("llm_compose", status="skipped", agent="cfo")
            return None
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
            # The provider billed this response whether or not the content
            # is usable — accumulate (never overwrite prior stages).
            latency_ms = round((perf_counter() - started) * 1000, 2)
            trace.add_usage(result.usage)
            trace.record_tool_call(
                "llm_compose", status="called", agent="cfo", latency_ms=latency_ms
            )
            if result.content:
                response_payload["reply"] = result.content
                trace.set_model_name(result.model_name or "deepseek-chat")
            return self._llm_stage_entry(
                trace,
                status="called" if result.content else "empty_content",
                usage=result.usage,
                model_name=result.model_name or "deepseek-chat",
                profile="chat",
                latency_ms=latency_ms,
            )
        except Exception as exc:
            logger.warning("LLM compose failed; deterministic reply kept: %s", exc)
            latency_ms = round((perf_counter() - started) * 1000, 2)
            trace.record_tool_call(
                "llm_compose", status="failed", agent="cfo", latency_ms=latency_ms
            )
            return self._llm_stage_entry(
                trace,
                status="failed",
                usage=None,
                model_name=None,
                profile="chat",
                latency_ms=latency_ms,
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
            "investment_research": context.get("investment_research"),
            "external_market_history": context.get("external_market_history"),
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
        has_investment_evidence = (
            (context.get("investment_research") or {}).get("status") == "available"
        )
        if not context.get("transactions_sample") and not has_investment_evidence:
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

        investment = context.get("investment_research") or {}
        if investment.get("status") == "available":
            symbol = str(investment.get("symbol") or "")
            quote = investment.get("quote") or {}
            quote_price = quote.get("price") or {}
            price = quote_price.get("amount")
            currency = quote_price.get("currency") or ""
            if language == "zh":
                reply = f"我已按只读研究流程核对 {symbol} 的有来源行情证据。"
                if price is not None:
                    reply += f"最近行情为 {currency} {price}。"
                reply += "历史行情不代表未来收益，也不会触发任何交易。"
            else:
                reply = f"I reviewed sourced {symbol} market evidence in read-only mode. "
                if price is not None:
                    reply += f"The latest quote is {currency} {price}. "
                reply += (
                    "Historical prices do not predict future returns, and no trade is executed."
                )
            if actions:
                reply += (
                    f"下一步：{actions[0].title}。"
                    if language == "zh"
                    else f" Next: {actions[0].title}."
                )
        elif investment.get("status") in {"symbol_required", "unavailable"}:
            reply = (
                "我还不能完成这次投资研究：请提供明确的股票或 ETF 代码，并确认行情数据源可用。"
                if language == "zh"
                else "I cannot complete this investment research yet: provide an explicit stock or ETF symbol and ensure the market-data source is available."
            )
        elif query_line:
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
            summary_cards=_response_summary_cards(context),
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

    def _finalize_trace(
        self, trace: TraceCollector, profile: dict[str, Any] | None = None
    ) -> None:
        stage_entries = trace.policy.get("llm_usage_by_stage") or {}
        cost_preferences = (profile or {}).get("cost_preferences") or {}
        reporting_currency = str(
            cost_preferences.get("reporting_currency")
            or get_settings().cost.reporting_currency
        )
        trace.set_cost(
            self.costing_service.cost_stage_entries(
                stage_entries,
                reporting_currency=reporting_currency,
                accounting_date=date.today(),
            )
        )

    def _log_trace(self, trace: TraceCollector) -> None:
        logger.info("Finance runtime trace", extra={"trace": trace.to_log_dict()})

    def _persist_trace(self, trace: TraceCollector) -> None:
        saved = save_agent_run_record_db(trace.to_run_record())
        if not saved:
            logger.debug("Agent run record was not persisted request_id=%s", trace.request_id)
