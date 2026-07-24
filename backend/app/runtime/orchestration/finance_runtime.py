"""Self-hosted CFO-first finance runtime."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.agents.cfo import CfoDecisionEngine
from app.config.settings import get_settings
from app.connectors.postgres.run_ledger_store import save_agent_run_record_db
from app.models.chat import ChatResponse
from app.models.turn_execution import TurnExecutionFacts
from app.models.runtime import AgentRunUsage
from app.runtime.capabilities import (
    CapabilityBindingError,
    CapabilityCatalog,
)
from app.runtime.contracts.output_validation import validate_output_contract
from app.runtime.execution import (
    AgentContext,
    ToolRegistry,
)
from app.runtime.execution.finance_turn_executor import FinanceTurnExecutor
from app.runtime.memory.finance_memory_extractor import extract_finance_memory
from app.runtime.memory.session_context import write_session_context
from app.runtime.observability.trace_collector import TraceCollector
from app.runtime.orchestration.intake import TurnContextualizer
from app.runtime.costing import CostingService
from app.runtime.response.cfo_reply_generator import CfoReplyGenerator
from app.runtime.response.finance_response_builder import FinanceResponseBuilder

logger = logging.getLogger(__name__)

def _excerpt(value: str, limit: int = 120) -> str:
    return " ".join((value or "").split())[:limit]


class FinanceRuntime:
    """Application runtime boundary for finance chat orchestration."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        capability_catalog: CapabilityCatalog,
        granted_capabilities: frozenset[str],
        turn_contextualizer: TurnContextualizer,
        decision_engine: CfoDecisionEngine,
        turn_executor: FinanceTurnExecutor,
        response_builder: FinanceResponseBuilder,
        reply_generator: CfoReplyGenerator,
        costing_service: CostingService,
    ) -> None:
        self.tool_registry = tool_registry
        self.capability_catalog = capability_catalog
        self.granted_capabilities = granted_capabilities
        self.turn_contextualizer = turn_contextualizer
        self.decision_engine = decision_engine
        self.turn_executor = turn_executor
        self.response_builder = response_builder
        self.reply_generator = reply_generator
        self.costing_service = costing_service

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
            )
            reply_language = self.response_builder.resolve_language(
                (profile or {}).get("preferences") or {},
                message,
            )
            try:
                execution_result = await self.turn_executor.execute(
                    capability_ids=capability_ids,
                    context=context,
                    reply_language=reply_language,
                    trace=trace,
                    policy_metadata={
                        "contextualization": contextualization_record,
                        "cfo_decision": decision_record,
                    },
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
            finance_context = execution_result.context
            response_payload = self.response_builder.build(
                context=finance_context,
                policy=execution_result.policy,
                specialist_outputs=execution_result.specialist_outputs,
            )
            response_payload["request_id"] = trace.request_id
            response_payload["execution"] = (
                execution_result.execution_facts.model_dump(mode="json")
            )
            if (
                on_pipeline_complete is not None
                and execution_result.projected_steps
            ):
                await on_pipeline_complete(
                    list(execution_result.projected_steps)
                )
            compose_result = await self.reply_generator.generate(
                context=finance_context,
                message=message,
                effective_message=effective_message,
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
