"""Execution of an approved CFO capability plan."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistExecutionBudget,
)
from app.models.external_market_data import ExternalMarketHistoryArtifact
from app.models.runtime import RuntimePolicyResult
from app.models.turn_execution import TurnExecutionFacts
from app.runtime.capabilities import (
    CapabilityCatalog,
    CapabilityHealthService,
    CapabilityResolver,
    bind_execution_plan,
)
from app.runtime.contracts.output_validation import validate_output_contract
from app.runtime.execution.artifact_registry import ArtifactRegistry
from app.runtime.execution.context import AgentContext
from app.runtime.execution.context_projector import ContextProjector
from app.runtime.execution.evidence_validation import (
    EvidenceJoiner,
    EvidenceValidationResult,
    EvidenceValidator,
    SpecialistArtifact,
)
from app.runtime.execution.finance_toolset import FinanceToolset
from app.runtime.execution.handoff import HandoffRequest, HandoffResult
from app.runtime.execution.planner import build_execution_plan
from app.runtime.execution.specialist_runner import SpecialistRunner
from app.runtime.execution.state import AgentState
from app.runtime.execution.tool_executor import (
    BoundedToolExecutor,
    ToolObservation,
    ToolRegistry,
)
from app.runtime.observability.steps_projection import project_steps
from app.runtime.observability.trace_collector import TraceCollector
from app.runtime.policy.audit_runner import should_run_audit
from app.runtime.policy.runtime_policy import evaluate_runtime_policy
from app.tools.mcp_market_data import project_external_history_for_specialist
from app.tools.web_research import WebResearchTool

SPECIALIST_TOOL_BY_AGENT = {
    "expense_analyst": "consult_expense_analyst",
    "budget_coach": "consult_budget_coach",
    "auditor": "consult_auditor",
    "market_context": "consult_market_context",
    "investment_research": "consult_investment_research",
}


@dataclass(frozen=True)
class FinanceTurnExecutionResult:
    context: dict[str, Any]
    policy: RuntimePolicyResult
    observations: tuple[ToolObservation, ...]
    specialist_outputs: dict[str, SpecialistAgentOutput]
    evidence_validation: EvidenceValidationResult
    execution_facts: TurnExecutionFacts
    projected_steps: tuple[dict[str, Any], ...]


class FinanceTurnExecutor:
    """Bind and execute the complete approved plan before response creation."""

    def __init__(
        self,
        *,
        capability_catalog: CapabilityCatalog,
        capability_resolver: CapabilityResolver,
        granted_capabilities: frozenset[str],
        tool_registry: ToolRegistry,
        toolset: FinanceToolset,
        specialist_runner: SpecialistRunner,
        web_research_tool: WebResearchTool,
        capability_health_service: CapabilityHealthService | None = None,
        context_projector: ContextProjector | None = None,
        evidence_joiner: EvidenceJoiner | None = None,
        evidence_validator: EvidenceValidator | None = None,
    ) -> None:
        self.capability_catalog = capability_catalog
        self.capability_resolver = capability_resolver
        self.granted_capabilities = granted_capabilities
        self.tool_registry = tool_registry
        self.toolset = toolset
        self.specialist_runner = specialist_runner
        self.web_research_tool = web_research_tool
        self.capability_health_service = capability_health_service
        self.context_projector = context_projector or ContextProjector()
        self.evidence_joiner = evidence_joiner or EvidenceJoiner()
        self.evidence_validator = evidence_validator or EvidenceValidator()

    async def execute(
        self,
        *,
        capability_ids: list[str],
        context: AgentContext,
        reply_language: str,
        trace: TraceCollector,
        policy_metadata: dict[str, Any],
    ) -> FinanceTurnExecutionResult:
        policy = evaluate_runtime_policy(
            capability_ids,
            self.capability_catalog,
        )
        trace.set_policy({**policy.model_dump(), **policy_metadata})
        context = replace(context, runtime_policy=policy.model_dump())

        effective_grants = set(self.granted_capabilities)
        if (
            "investment.external_market_history" in capability_ids
            and self.capability_health_service is not None
        ):
            status = (
                await self.capability_health_service.vibe_market_data_status()
            )
            if not status.available:
                effective_grants.discard(
                    "investment.external_market_history"
                )

        plan = build_execution_plan(
            capability_ids,
            policy,
            self.capability_catalog,
        )
        bound_plan = bind_execution_plan(
            plan,
            self.capability_resolver,
            granted_capabilities=effective_grants,
        )

        state = AgentState(selected_agents=list(bound_plan.selected_agents))
        artifacts = ArtifactRegistry()
        trace.select_agents(list(bound_plan.selected_agents))
        trace.set_tools_available(
            [
                *[spec.name for spec in self.tool_registry.available()],
                *SPECIALIST_TOOL_BY_AGENT.values(),
            ]
        )

        web_research_budget = (
            self.web_research_tool.new_budget()
            if "search_web_research" in bound_plan.tool_names
            else None
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

        finance_context = self._finance_context(
            context=context,
            artifacts=artifacts,
            capability_ids=capability_ids,
            reply_language=reply_language,
            trace=trace,
        )
        specialist_outputs, evidence_validation = self._run_specialists(
            handoff_names=bound_plan.handoff_names,
            finance_context=finance_context,
            artifacts=artifacts,
            policy=policy,
            state=state,
            trace=trace,
        )
        projected_steps = tuple(
            project_steps(
                {
                    "tool_calls": [
                        call.model_dump() for call in trace.tool_calls
                    ],
                    "handoffs": [
                        handoff.model_dump() for handoff in trace.handoffs
                    ],
                }
            )
        )
        execution_facts = TurnExecutionFacts(
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
        trace.policy["turn_execution"] = execution_facts.model_dump(
            mode="json"
        )
        return FinanceTurnExecutionResult(
            context=finance_context,
            policy=policy,
            observations=tuple(state.tool_observations),
            specialist_outputs=specialist_outputs,
            evidence_validation=evidence_validation,
            execution_facts=execution_facts,
            projected_steps=projected_steps,
        )

    def _finance_context(
        self,
        *,
        context: AgentContext,
        artifacts: ArtifactRegistry,
        capability_ids: list[str],
        reply_language: str,
        trace: TraceCollector,
    ) -> dict[str, Any]:
        result = artifacts.get("get_finance_context") or {
            "user_id": context.user_id,
            "profile": context.profile,
            "message": context.effective_message,
            "runtime_policy": context.runtime_policy,
        }
        result = {**result, "reply_language": reply_language}

        for artifact_name, context_key in (
            ("get_expense_snapshot", "expense_snapshot"),
            ("get_budget_snapshot", "budget_snapshot"),
            ("get_anomaly_summary", "anomaly_summary"),
            ("get_cashflow_summary", "cashflow_summary"),
        ):
            artifact = artifacts.get(artifact_name)
            if artifact is not None:
                result = {**result, context_key: artifact}

        import_quality = artifacts.get("get_import_quality_report")
        if import_quality and import_quality.get("reports"):
            result = {**result, "import_quality": import_quality}
        query_result = artifacts.get("query_transactions")
        if query_result is not None:
            result = {**result, "transaction_query": query_result}
        investment_research = artifacts.get(
            "get_investment_research_context"
        )
        if investment_research:
            result = {
                **result,
                "investment_research": investment_research,
            }

        external_market_history = artifacts.get("get_vibe_market_data")
        if external_market_history:
            artifact = ExternalMarketHistoryArtifact.model_validate(
                external_market_history
            )
            result = {
                **result,
                "external_market_history": external_market_history,
                "investment_research": (
                    project_external_history_for_specialist(artifact)
                ),
            }
        elif "investment.external_market_history" in capability_ids:
            result = {
                **result,
                "investment_research": {
                    "status": "unavailable",
                    "reason": (
                        "The requested external MCP market-data capability "
                        "is disabled or unavailable."
                    ),
                    "trade_actions_allowed": False,
                },
            }

        web_research = artifacts.get("search_web_research")
        if web_research:
            result = {**result, "web_research": web_research}
        knowledge_result = artifacts.get("search_knowledge")
        if knowledge_result:
            result = {
                **result,
                "knowledge_retrieval": knowledge_result,
            }
            trace.policy["knowledge_evidence"] = [
                self.toolset.knowledge_ledger_projection(item)
                for item in knowledge_result.get("artifacts") or []
            ]
        return result

    def _run_specialists(
        self,
        *,
        handoff_names: list[str],
        finance_context: dict[str, Any],
        artifacts: ArtifactRegistry,
        policy: RuntimePolicyResult,
        state: AgentState,
        trace: TraceCollector,
    ) -> tuple[
        dict[str, SpecialistAgentOutput],
        EvidenceValidationResult,
    ]:
        specialist_artifacts: list[SpecialistArtifact] = []
        for specialist in [
            name for name in handoff_names if name != "auditor"
        ]:
            projected = self.context_projector.project(
                specialist,
                finance_context=finance_context,
                artifacts=artifacts,
            )
            request = HandoffRequest(
                from_agent="cfo",
                to_agent=specialist,
                task=f"Produce {specialist} review for CFO response",
                evidence=projected.evidence,
                artifact_refs=projected.artifact_refs,
                allowed_tools=(),
                constraints=[
                    "Use loaded evidence only",
                    "Call out limitations",
                ],
                budget=self._handoff_budget(policy),
                output_contract="SpecialistAgentOutput",
            )
            result = self._run_handoff(request)
            self._record_handoff(
                result=result,
                specialist=specialist,
                state=state,
                trace=trace,
            )
            _, validation = validate_output_contract(
                agent=specialist,
                contract="SpecialistAgentOutput",
                model_type=SpecialistAgentOutput,
                payload=result.output,
            )
            trace.record_output_validation(validation)
            if validation.status == "passed":
                specialist_artifacts.append(
                    SpecialistArtifact(
                        specialist=specialist,
                        output=SpecialistAgentOutput.model_validate(
                            result.output
                        ),
                        artifact_refs=projected.artifact_refs,
                    )
                )

        bundle = self.evidence_joiner.join(
            artifacts,
            specialist_artifacts,
        )
        evidence_validation = self.evidence_validator.validate(bundle)
        trace.policy["evidence_validation"] = (
            evidence_validation.ledger_dump()
        )
        outputs = bundle.outputs_for(
            evidence_validation.accepted_specialists
        )

        if "auditor" in handoff_names and should_run_audit(
            policy,
            specialists_used=list(outputs),
        ):
            projected = self.context_projector.project(
                "auditor",
                finance_context=finance_context,
                artifacts=artifacts,
            )
            request = HandoffRequest(
                from_agent="cfo",
                to_agent="auditor",
                task=(
                    "Audit CFO and specialist evidence before final response"
                ),
                evidence={
                    "finance_context": projected.evidence,
                    "specialists": {
                        key: value.model_dump()
                        for key, value in outputs.items()
                    },
                },
                artifact_refs=projected.artifact_refs,
                allowed_tools=(),
                constraints=[
                    "No investment/tax/legal advice",
                    "Expose uncertainty",
                ],
                budget=self._handoff_budget(policy),
                output_contract="SpecialistAgentOutput",
            )
            result = self._run_handoff(request, policy=policy)
            self._record_handoff(
                result=result,
                specialist="auditor",
                state=state,
                trace=trace,
            )
            _, validation = validate_output_contract(
                agent="auditor",
                contract="SpecialistAgentOutput",
                model_type=SpecialistAgentOutput,
                payload=result.output,
            )
            trace.record_output_validation(validation)
            if validation.status == "passed":
                outputs["auditor"] = SpecialistAgentOutput.model_validate(
                    result.output
                )
        return outputs, evidence_validation

    @staticmethod
    def _handoff_budget(
        policy: RuntimePolicyResult,
    ) -> SpecialistExecutionBudget:
        output_tokens = {
            "simple": 800,
            "moderate": 1200,
            "complex": 1600,
        }[policy.complexity]
        timeout_ms = {
            "simple": 3000,
            "moderate": 5000,
            "complex": 8000,
        }[policy.complexity]
        return SpecialistExecutionBudget(
            max_tool_calls=0,
            max_output_tokens=output_tokens,
            timeout_ms=timeout_ms,
        )

    def _run_handoff(
        self,
        request: HandoffRequest,
        *,
        policy: RuntimePolicyResult | None = None,
    ) -> HandoffResult:
        return self.specialist_runner.run(request, policy=policy)

    @staticmethod
    def _record_handoff(
        *,
        result: HandoffResult,
        specialist: str,
        state: AgentState,
        trace: TraceCollector,
    ) -> None:
        state.record_handoff_result(result)
        trace.record_handoff(
            from_agent=result.from_agent,
            to_agent=result.to_agent,
            status=result.status,
            reason="typed_internal_handoff",
            output=(
                _bounded_handoff_output(result.output)
                if result.output
                else None
            ),
        )
        trace.record_tool_call(
            SPECIALIST_TOOL_BY_AGENT[specialist],
            status=(
                "called" if result.status == "completed" else "failed"
            ),
            agent="cfo",
            latency_ms=result.latency_ms,
        )

    @staticmethod
    def _has_projectable_evidence(
        observation: ToolObservation,
    ) -> bool:
        if not observation.success or not observation.result:
            return False
        return observation.result.get("status") not in {
            "unavailable",
            "symbol_required",
        }


def _bounded_handoff_output(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "specialist": output.get("specialist"),
        "findings": output.get("findings") or [],
        "recommendations": output.get("recommendations") or [],
        "limitations": output.get("limitations") or [],
    }
