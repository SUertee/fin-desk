"""Self-hosted CFO-first finance runtime."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from time import perf_counter
from typing import Any

from app.agents.cfo import CfoDecisionEngine
from app.agents.specialists.contracts import SpecialistAgentOutput
from app.connectors.postgres.run_ledger_store import save_agent_run_record_db
from app.connectors.postgres.exchange_rate_store import get_exchange_rate_snapshot_db
from app.connectors.postgres.statement_import_store import list_latest_quality_reports_db
from app.models.chat import ChatResponse
from app.models.turn_execution import TurnExecutionFacts
from app.knowledge import KnowledgeQuery, KnowledgeRetriever
from app.knowledge.factory import build_knowledge_retriever
from app.models.external_market_data import ExternalMarketHistoryArtifact
from app.models.runtime import AgentRunUsage, RuntimePolicyResult
from app.runtime.capabilities import (
    CapabilityBindingError,
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
from app.runtime.observability.steps_projection import project_steps
from app.runtime.orchestration.intake import ModelTurnContextualizer, TurnContextualizer
from app.runtime.policy.audit_runner import should_run_audit
from app.runtime.policy.runtime_policy import evaluate_runtime_policy
from app.runtime.costing import CostingService
from app.config.settings import get_settings
from app.runtime.llm.deepseek_client import DeepSeekTextClient
from app.runtime.response.cfo_reply_generator import CfoReplyGenerator
from app.runtime.response.finance_response_builder import FinanceResponseBuilder
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


def _bounded_handoff_output(output: dict[str, Any]) -> dict[str, Any]:
    """Evidence-safe subset of a specialist output for the run ledger."""

    return {
        "specialist": output.get("specialist"),
        "findings": output.get("findings") or [],
        "recommendations": output.get("recommendations") or [],
        "limitations": output.get("limitations") or [],
    }


def _excerpt(value: str, limit: int = 120) -> str:
    return " ".join((value or "").split())[:limit]


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
        knowledge_retriever: KnowledgeRetriever | None = None,
        decision_engine: CfoDecisionEngine | None = None,
        response_builder: FinanceResponseBuilder | None = None,
        reply_generator: CfoReplyGenerator | None = None,
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
        self.knowledge_retriever = knowledge_retriever or build_knowledge_retriever()
        self.decision_engine = decision_engine or CfoDecisionEngine(
            lambda: self.llm_client
        )
        self.turn_contextualizer = TurnContextualizer(
            model=ModelTurnContextualizer(lambda: self.llm_client)
        )
        self.response_builder = response_builder or FinanceResponseBuilder()
        self.reply_generator = reply_generator or CfoReplyGenerator(
            lambda: self.llm_client,
            self.response_builder.resolve_language,
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
        # CFO Room session scope; empty uses the default chat scope.
        session_id: str = "",
        entrypoint: str = "chat",
        on_reply_delta=None,
        on_pipeline_complete=None,
    ) -> dict[str, Any]:
        trace = TraceCollector.start_run(
            user_id=user_id,
            entrypoint=entrypoint,
            runtime_requested="self_hosted",
        )
        trace.set_output_contract("ChatResponse")

        try:
            # Resolve follow-up references before the CFO chooses an action.
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
                if intake.model_name:
                    trace.set_model_name(intake.model_name)

            decision_capabilities = tuple(
                item.descriptor
                for item in self.capability_catalog.list()
                if item.status.enabled
                and item.status.available
                and item.descriptor.capability_id in self.granted_capabilities
            )
            decision_result = await self.decision_engine.decide(
                effective_message,
                capabilities=decision_capabilities,
                chat_history=chat_history,
                memory_context=memory_context or {},
                profile=profile,
                needs_clarification=(
                    turn.resolution_status == "needs_clarification"
                ),
            )
            if decision_result.status in {"called", "invalid_output", "failed"}:
                trace.record_tool_call(
                    "cfo_decide",
                    status="called" if decision_result.status == "called" else "failed",
                    agent="cfo",
                    latency_ms=decision_result.latency_ms,
                )
                trace.add_usage(decision_result.usage)
                llm_stages["cfo_decide"] = self._llm_stage_entry(
                    trace,
                    status=decision_result.status,
                    usage=decision_result.usage,
                    model_name=decision_result.model_name,
                    profile="router",
                    latency_ms=decision_result.latency_ms,
                )
                if decision_result.model_name:
                    trace.set_model_name(decision_result.model_name)
            decision = decision_result.decision
            decision_record = {
                "stage": "cfo_decision",
                "status": decision_result.status,
                "action": decision.action if decision else None,
                "capability_ids": [
                    request.capability_id
                    for request in (decision.capability_requests if decision else ())
                ],
            }
            trace.set_policy(
                {
                    "contextualization": contextualization_record,
                    "cfo_decision": decision_record,
                }
            )
            trace.select_agents(["cfo"])
            trace.set_input_summary(
                self._input_summary(
                    message=message,
                    transactions=transactions,
                    monthly_totals=monthly_totals,
                    chat_history=chat_history,
                    memory_context=memory_context or {},
                )
            )

            if decision is None:
                execution = TurnExecutionFacts(outcome="failed")
                trace.policy["turn_execution"] = execution.model_dump(mode="json")
                response_payload = {
                    "reply": self._decision_failure_reply(profile, message),
                    "agent_used": "cfo",
                    "request_id": trace.request_id,
                    "data": None,
                    "execution": execution.model_dump(mode="json"),
                }
                return self._complete_turn(trace, profile, response_payload, llm_stages)

            if decision.action in {"direct_response", "ask_clarification"}:
                outcome = (
                    "direct_response"
                    if decision.action == "direct_response"
                    else "clarification"
                )
                execution = TurnExecutionFacts(outcome=outcome)
                trace.policy["turn_execution"] = execution.model_dump(mode="json")
                response_payload = {
                    "reply": decision.reply or "",
                    "agent_used": "cfo",
                    "request_id": trace.request_id,
                    "data": None,
                    "execution": execution.model_dump(mode="json"),
                }
                return self._complete_turn(trace, profile, response_payload, llm_stages)

            capability_ids = [
                request.capability_id for request in decision.capability_requests
            ]
            policy = evaluate_runtime_policy(capability_ids, self.capability_catalog)
            trace.set_policy(
                {
                    **policy.model_dump(),
                    "contextualization": contextualization_record,
                    "cfo_decision": decision_record,
                }
            )
            context = AgentContext(
                request_id=trace.request_id,
                user_id=user_id,
                entrypoint=entrypoint,
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
            effective_grants = set(self.granted_capabilities)
            if (
                "investment.external_market_history" in capability_ids
                and self.capability_health_service is not None
            ):
                mcp_status = (
                    await self.capability_health_service.vibe_market_data_status()
                )
                if not mcp_status.available:
                    effective_grants.discard(
                        "investment.external_market_history"
                    )
            plan = build_execution_plan(
                capability_ids,
                policy,
                self.capability_catalog,
            )
            try:
                bound_plan = bind_execution_plan(
                    plan,
                    self.capability_resolver,
                    granted_capabilities=effective_grants,
                )
            except CapabilityBindingError as exc:
                execution = TurnExecutionFacts(
                    outcome="blocked",
                    policy_blocked=True,
                )
                trace.policy["capability_rejection"] = {
                    "capability_id": exc.capability_id,
                    "status": exc.status,
                    "reason": exc.reason,
                }
                trace.policy["turn_execution"] = execution.model_dump(mode="json")
                response_payload = {
                    "reply": self._capability_blocked_reply(profile, message),
                    "agent_used": "cfo",
                    "request_id": trace.request_id,
                    "data": None,
                    "execution": execution.model_dump(mode="json"),
                }
                return self._complete_turn(trace, profile, response_payload, llm_stages)
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
                self._input_summary(
                    message=message,
                    transactions=transactions,
                    monthly_totals=monthly_totals,
                    chat_history=chat_history,
                    memory_context=context.memory_context,
                )
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

            finance_context = artifacts.get("get_finance_context") or {
                "user_id": context.user_id,
                "profile": context.profile,
                "message": context.effective_message,
                "runtime_policy": context.runtime_policy,
            }
            reply_language = self.response_builder.resolve_language(
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
            elif "investment.external_market_history" in capability_ids:
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
            knowledge_result = artifacts.get("search_knowledge")
            if knowledge_result:
                finance_context = {
                    **finance_context,
                    "knowledge_retrieval": knowledge_result,
                }
                trace.policy["knowledge_evidence"] = [
                    self._knowledge_ledger_projection(item)
                    for item in knowledge_result.get("artifacts") or []
                ]
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

            response_payload = self.response_builder.build(
                context=finance_context,
                policy=policy,
                specialist_outputs=specialist_outputs,
            )
            response_payload["request_id"] = trace.request_id
            projected_steps = project_steps(
                {
                    "tool_calls": [tc.model_dump() for tc in trace.tool_calls],
                    "handoffs": [h.model_dump() for h in trace.handoffs],
                }
            )
            execution = TurnExecutionFacts(
                outcome="executed",
                evidence_available=any(
                    self._has_projectable_evidence(observation)
                    for observation in state.tool_observations
                ),
                specialist_findings_available=any(
                    name != "auditor" and output.findings
                    for name, output in specialist_outputs.items()
                ),
                process_available=bool(projected_steps),
            )
            response_payload["execution"] = execution.model_dump(mode="json")
            trace.policy["turn_execution"] = execution.model_dump(mode="json")
            if on_pipeline_complete is not None and projected_steps:
                await on_pipeline_complete(projected_steps)
            compose_result = await self.reply_generator.generate(
                context=finance_context,
                message=message,
                effective_message=effective_message,
                chat_history=chat_history,
                response_payload=response_payload,
                on_reply_delta=on_reply_delta,
            )
            if compose_result.status == "skipped":
                trace.record_tool_call(
                    "llm_compose",
                    status="skipped",
                    agent="cfo",
                )
            else:
                trace.add_usage(compose_result.usage)
                trace.record_tool_call(
                    "llm_compose",
                    status=(
                        "failed"
                        if compose_result.status == "failed"
                        else "called"
                    ),
                    agent="cfo",
                    latency_ms=compose_result.latency_ms,
                )
                if compose_result.reply is not None:
                    response_payload["reply"] = compose_result.reply
                if compose_result.status in {"called", "policy_blocked"} and (
                    finance_context.get("investment_research")
                ):
                    trace.policy["investment_output_guard"] = {
                        "status": (
                            "blocked"
                            if compose_result.policy_violations
                            else "passed"
                        ),
                        "violations": list(
                            compose_result.policy_violations
                        ),
                    }
                if compose_result.model_name:
                    trace.set_model_name(compose_result.model_name)
                llm_stages["llm_compose"] = self._llm_stage_entry(
                    trace,
                    status=compose_result.status,
                    usage=compose_result.usage,
                    model_name=compose_result.model_name or "deepseek-chat",
                    profile="chat",
                    latency_ms=compose_result.latency_ms,
                )
            if llm_stages:
                trace.policy["llm_usage_by_stage"] = llm_stages
            audit = (response_payload.get("data") or {}).get("audit")
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
            return self._complete_turn(trace, profile, response_payload, llm_stages)
        except Exception as exc:
            trace.fail(exc)
            self._finalize_trace(trace, profile)
            self._log_trace(trace)
            self._persist_trace(trace)
            raise

    def _complete_turn(
        self,
        trace: TraceCollector,
        profile: dict[str, Any],
        response_payload: dict[str, Any],
        llm_stages: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        if llm_stages:
            trace.policy["llm_usage_by_stage"] = llm_stages
        _, validation = validate_output_contract(
            agent="cfo",
            contract="ChatResponse",
            model_type=ChatResponse,
            payload=response_payload,
        )
        trace.record_output_validation(validation)
        if validation.status == "failed":
            raise ValueError("FinanceRuntime returned invalid ChatResponse")
        trace.mark_runtime_used("self_hosted")
        self._finalize_trace(trace, profile)
        self._log_trace(trace)
        self._persist_trace(trace)
        return response_payload

    @staticmethod
    def _input_summary(
        *,
        message: str,
        transactions: list[dict[str, Any]],
        monthly_totals: list[dict[str, Any]],
        chat_history: list[dict[str, Any]],
        memory_context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "message_length": len(message or ""),
            "transaction_count": len(transactions),
            "monthly_total_count": len(monthly_totals),
            "chat_history_count": len(chat_history),
            "memory_recent_turns_count": len(memory_context.get("recent_turns") or []),
            "memory_session_state_present": bool(memory_context.get("session_memory")),
            "memory_truncated": bool(memory_context.get("truncated")),
            "memory_summary_used": bool(memory_context.get("summary_used")),
        }

    @staticmethod
    def _has_projectable_evidence(observation: ToolObservation) -> bool:
        if not observation.success or not observation.result:
            return False
        return observation.result.get("status") not in {
            "unavailable",
            "symbol_required",
        }

    def _decision_failure_reply(
        self, profile: dict[str, Any], message: str
    ) -> str:
        language = self.response_builder.resolve_language(
            (profile or {}).get("preferences") or {}, message
        )
        if language == "zh":
            return "CFO 暂时无法判断这一步该如何处理，请稍后重试。"
        return "The CFO could not decide how to handle this turn. Please try again."

    def _capability_blocked_reply(
        self, profile: dict[str, Any], message: str
    ) -> str:
        language = self.response_builder.resolve_language(
            (profile or {}).get("preferences") or {}, message
        )
        if language == "zh":
            return "这项能力当前未启用或不可用，因此没有执行。"
        return "This capability is disabled or unavailable, so nothing was executed."

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

        turn = intake.turn
        return {
            "stage": "turn_contextualization",
            "raw_message_excerpt": _excerpt(raw_message),
            "effective_message_excerpt": (
                _excerpt(turn.effective_message) if turn.rewrite_applied else ""
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
                name="search_knowledge",
                description="Search reviewed finance guidance with bounded lexical retrieval.",
                executor=self._tool_search_knowledge,
                owner="knowledge",
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

    async def _tool_search_knowledge(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        try:
            result = self.knowledge_retriever.retrieve(
                KnowledgeQuery(text=context.effective_message, top_k=4)
            )
        except Exception as exc:
            logger.warning("Knowledge retrieval unavailable: %s", type(exc).__name__)
            return ToolObservation(
                tool_name="search_knowledge",
                success=False,
                agent=str(payload.get("agent") or "cfo"),
                purpose="reviewed_knowledge_evidence",
                error_class=type(exc).__name__,
                error_message="Reviewed knowledge is currently unavailable.",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        return ToolObservation(
            tool_name="search_knowledge",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="reviewed_knowledge_evidence",
            result=result.model_dump(mode="json"),
            evidence_refs=[item.citation_id for item in result.artifacts],
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    @staticmethod
    def _knowledge_ledger_projection(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item.get(key)
            for key in (
                "citation_id",
                "document_id",
                "chunk_id",
                "title",
                "section",
                "excerpt",
                "source_url",
                "source_authority",
                "jurisdiction",
                "reviewed_at",
                "review_after",
                "freshness",
                "retrieval_method",
            )
        }

    async def _tool_investment_research_context(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        reference = extract_instrument_reference(context.effective_message)
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
        filters = extract_query_filters(context.effective_message)
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
            "message": context.effective_message,
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
