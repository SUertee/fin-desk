"""Structured trace metadata for finance agent runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.models.runtime import (
    AgentHandoff,
    AgentInputSummary,
    AgentOutputValidation,
    AgentRunCost,
    AgentRunRecord,
    AgentRunUsage,
    AgentToolCall,
    RuntimeEntrypoint,
)


@dataclass
class TraceCollector:
    user_id: str
    entrypoint: RuntimeEntrypoint
    runtime_requested: str
    request_id: str = field(default_factory=lambda: str(uuid4()))
    runtime_used: str | None = None
    model_name: str | None = None
    error_type: str | None = None
    policy: dict[str, Any] = field(default_factory=dict)
    selected_agents: list[str] = field(default_factory=list)
    tools_available: list[str] = field(default_factory=list)
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    handoffs: list[AgentHandoff] = field(default_factory=list)
    output_validations: list[AgentOutputValidation] = field(default_factory=list)
    output_contract: str | None = None
    audit_status: str | None = None
    input_summary: AgentInputSummary = field(default_factory=AgentInputSummary)
    usage: AgentRunUsage = field(default_factory=AgentRunUsage)
    cost: AgentRunCost = field(default_factory=AgentRunCost)
    _started_at: float = field(default_factory=perf_counter)

    @classmethod
    def start_run(
        cls,
        *,
        user_id: str,
        entrypoint: RuntimeEntrypoint,
        runtime_requested: str,
    ) -> "TraceCollector":
        return cls(
            user_id=user_id,
            entrypoint=entrypoint,
            runtime_requested=runtime_requested,
        )

    def set_policy(self, policy: dict[str, Any]) -> None:
        self.policy = policy

    def set_input_summary(self, summary: AgentInputSummary | dict[str, Any]) -> None:
        self.input_summary = AgentInputSummary.model_validate(summary)

    def select_agents(self, agents: list[str]) -> None:
        self.selected_agents = list(dict.fromkeys(agents))

    def set_tools_available(self, tools: list[str]) -> None:
        self.tools_available = tools

    def record_tool_call(
        self,
        name: str,
        *,
        status: str = "expected",
        agent: str | None = None,
        latency_ms: float | None = None,
    ) -> None:
        for tool_call in self.tool_calls:
            if tool_call.name != name:
                continue
            if tool_call.status == "expected" and status != "expected":
                tool_call.status = status
                tool_call.agent = agent or tool_call.agent
                tool_call.latency_ms = (
                    latency_ms if latency_ms is not None else tool_call.latency_ms
                )
                return
            if tool_call.status == status and tool_call.agent == agent:
                tool_call.latency_ms = (
                    latency_ms if latency_ms is not None else tool_call.latency_ms
                )
                return
        self.tool_calls.append(
            AgentToolCall.model_validate(
                {
                    "name": name,
                    "status": status,
                    "agent": agent,
                    "latency_ms": latency_ms,
                }
            )
        )

    def record_handoff(
        self,
        *,
        from_agent: str,
        to_agent: str,
        status: str = "planned",
        reason: str | None = None,
        output: dict | None = None,
    ) -> None:
        for handoff in self.handoffs:
            if handoff.from_agent != from_agent or handoff.to_agent != to_agent:
                continue
            if handoff.status == "planned" and status == "completed":
                handoff.status = status
                handoff.reason = reason or handoff.reason
                handoff.output = output if output is not None else handoff.output
                return
            if handoff.status == status:
                return
        self.handoffs.append(
            AgentHandoff.model_validate(
                {
                    "output": output,
                    "from_agent": from_agent,
                    "to_agent": to_agent,
                    "status": status,
                    "reason": reason,
                }
            )
        )

    def record_observations(
        self,
        *,
        tool_calls: list[AgentToolCall],
        handoffs: list[AgentHandoff],
        output_validations: list[AgentOutputValidation] | None = None,
        usage: AgentRunUsage | None = None,
    ) -> None:
        for tool_call in tool_calls:
            self.record_tool_call(
                tool_call.name,
                status=tool_call.status,
                agent=tool_call.agent,
                latency_ms=tool_call.latency_ms,
            )
        for handoff in handoffs:
            self.record_handoff(
                from_agent=handoff.from_agent,
                to_agent=handoff.to_agent,
                status=handoff.status,
                reason=handoff.reason,
            )
        for validation in output_validations or []:
            self.record_output_validation(validation)
        if usage is not None:
            self.set_usage(usage)

    def record_output_validation(
        self,
        validation: AgentOutputValidation | dict[str, Any],
    ) -> None:
        parsed = AgentOutputValidation.model_validate(validation)
        for existing in self.output_validations:
            if existing.agent != parsed.agent or existing.contract != parsed.contract:
                continue
            existing.status = parsed.status
            existing.errors = parsed.errors
            return
        self.output_validations.append(parsed)

    def set_usage(self, usage: AgentRunUsage | dict[str, Any]) -> None:
        """Overwrite semantics — kept for existing single-stage callers."""

        self.usage = AgentRunUsage.model_validate(usage)

    def add_usage(self, usage: AgentRunUsage | dict[str, Any] | None) -> None:
        """Accumulate one LLM stage's usage into the run total.

        Multiple stages (route_classify, turn_contextualize, llm_compose)
        each add their share; None or empty payloads are safe no-ops.
        """

        if usage is None:
            return
        parsed = AgentRunUsage.model_validate(usage)
        self.usage = AgentRunUsage(
            request_count=self.usage.request_count + parsed.request_count,
            model_response_count=(
                self.usage.model_response_count + parsed.model_response_count
            ),
            input_tokens=self.usage.input_tokens + parsed.input_tokens,
            output_tokens=self.usage.output_tokens + parsed.output_tokens,
            total_tokens=self.usage.total_tokens + parsed.total_tokens,
        )

    def set_model_name(self, model_name: str | None) -> None:
        self.model_name = model_name

    def set_cost(self, cost: AgentRunCost | dict[str, Any]) -> None:
        self.cost = AgentRunCost.model_validate(cost)

    def set_output_contract(self, contract: str) -> None:
        self.output_contract = contract

    def set_audit_status(self, status: str | None) -> None:
        self.audit_status = status

    def mark_runtime_used(self, runtime: str) -> None:
        self.runtime_used = runtime

    def fail(self, error: Exception) -> None:
        self.error_type = type(error).__name__

    def to_run_record(self) -> AgentRunRecord:
        return AgentRunRecord(
            request_id=self.request_id,
            entrypoint=self.entrypoint,
            user_id=self.user_id,
            runtime_requested=self.runtime_requested,
            runtime_used=self.runtime_used,
            model_name=self.model_name,
            selected_agents=self.selected_agents,
            tools_available=self.tools_available,
            tool_calls=self.tool_calls,
            handoffs=self.handoffs,
            output_validations=self.output_validations,
            output_contract=self.output_contract,
            audit_status=self.audit_status,
            input_summary=self.input_summary,
            policy=self.policy,
            usage=self.usage,
            cost=self.cost,
            latency_ms=round((perf_counter() - self._started_at) * 1000, 2),
            error_type=self.error_type,
        )

    def to_log_dict(self) -> dict[str, Any]:
        return self.to_run_record().model_dump()
