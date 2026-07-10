"""Normalize OpenAI Agents SDK run observations for the harness trace."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from app.agents.specialists.contracts import SpecialistAgentOutput
from app.models.runtime import (
    AgentHandoff,
    AgentOutputValidation,
    AgentRunUsage,
    AgentToolCall,
)
from app.runtime.contracts.output_validation import validate_output_contract


SPECIALIST_AGENT_BY_TOOL = {
    "consult_expense_analyst": "expense_analyst",
    "consult_budget_coach": "budget_coach",
    "consult_auditor": "auditor",
}


@dataclass
class RunObservations:
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    handoffs: list[AgentHandoff] = field(default_factory=list)
    output_validations: list[AgentOutputValidation] = field(default_factory=list)
    usage: AgentRunUsage = field(default_factory=AgentRunUsage)


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _agent_name(agent: Any) -> str | None:
    if agent is None:
        return None
    name = _value(agent, "name")
    return str(name) if name else str(agent)


def _raw_tool_name(raw_item: Any) -> str | None:
    for attr in ("name", "tool_name"):
        value = _value(raw_item, attr)
        if value:
            return str(value)

    function = _value(raw_item, "function")
    function_name = _value(function, "name")
    if function_name:
        return str(function_name)

    return None


def _tool_name(item: Any) -> str | None:
    for attr in ("tool_name", "name"):
        value = _value(item, attr)
        if value:
            return str(value)
    return _raw_tool_name(_value(item, "raw_item"))


def _tool_call_id(item: Any) -> str | None:
    for source in (item, _value(item, "raw_item")):
        for attr in ("call_id", "tool_call_id", "id"):
            value = _value(source, attr)
            if value:
                return str(value)
    return None


def _tool_output_payload(item: Any) -> Any:
    for source in (item, _value(item, "raw_item")):
        if source is None:
            continue
        for attr in ("output", "result", "content"):
            value = _value(source, attr)
            if value is not None:
                return value
    return None


def _json_payload(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _specialist_output_validation(
    *,
    tool_name: str | None,
    output_payload: Any,
) -> AgentOutputValidation | None:
    specialist = SPECIALIST_AGENT_BY_TOOL.get(tool_name or "")
    if not specialist:
        return None

    _, validation = validate_output_contract(
        agent=specialist,
        contract="SpecialistAgentOutput",
        model_type=SpecialistAgentOutput,
        payload=_json_payload(output_payload),
    )
    return validation


def _tool_context_name(context: Any) -> str | None:
    return _value(context, "tool_name") or _value(context, "name")


def _handoff_target_from_tool(tool_name: str | None) -> str | None:
    if not tool_name:
        return None
    if tool_name.startswith("transfer_to_"):
        return tool_name.removeprefix("transfer_to_")
    return None


def _item_type(item: Any) -> str:
    value = _value(item, "type")
    if value:
        return str(value)
    return type(item).__name__


def _dedupe_tool_calls(tool_calls: list[AgentToolCall]) -> list[AgentToolCall]:
    seen: set[tuple[str, str | None]] = set()
    deduped: list[AgentToolCall] = []
    for call in tool_calls:
        key = (call.name, call.agent)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(call)
    return deduped


def _merge_tool_calls(tool_calls: list[AgentToolCall]) -> list[AgentToolCall]:
    merged: dict[tuple[str, str | None], AgentToolCall] = {}
    for call in tool_calls:
        key = (call.name, call.agent)
        existing = merged.get(key)
        if existing is None:
            merged[key] = call
            continue
        if existing.latency_ms is None and call.latency_ms is not None:
            existing.latency_ms = call.latency_ms
        if existing.status == "expected" and call.status != "expected":
            existing.status = call.status
    return list(merged.values())


def _dedupe_handoffs(handoffs: list[AgentHandoff]) -> list[AgentHandoff]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[AgentHandoff] = []
    for handoff in handoffs:
        key = (handoff.from_agent, handoff.to_agent, handoff.status)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(handoff)
    return deduped


def _dedupe_output_validations(
    output_validations: list[AgentOutputValidation],
) -> list[AgentOutputValidation]:
    merged: dict[tuple[str, str], AgentOutputValidation] = {}
    for validation in output_validations:
        merged[(validation.agent, validation.contract)] = validation
    return list(merged.values())


def merge_run_observations(*observations: RunObservations) -> RunObservations:
    merged = RunObservations()
    for item in observations:
        merged.tool_calls.extend(item.tool_calls)
        merged.handoffs.extend(item.handoffs)
        merged.output_validations.extend(item.output_validations)
        if (
            item.usage.total_tokens
            or item.usage.input_tokens
            or item.usage.output_tokens
            or item.usage.request_count
        ):
            merged.usage = item.usage
    merged.tool_calls = _merge_tool_calls(merged.tool_calls)
    merged.handoffs = _dedupe_handoffs(merged.handoffs)
    merged.output_validations = _dedupe_output_validations(
        merged.output_validations
    )
    return merged


def _int_value(item: Any, names: tuple[str, ...]) -> int:
    for name in names:
        value = _value(item, name)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
    return 0


def _usage_from_context_wrapper(result: Any) -> AgentRunUsage:
    context_wrapper = _value(result, "context_wrapper")
    usage = _value(context_wrapper, "usage")
    if usage is None:
        return AgentRunUsage()

    request_usage_entries = _value(usage, "request_usage_entries", []) or []
    request_count = _int_value(usage, ("requests", "request_count"))
    if request_count == 0:
        request_count = len(request_usage_entries)

    return AgentRunUsage(
        request_count=request_count,
        model_response_count=request_count,
        input_tokens=_int_value(usage, ("input_tokens", "prompt_tokens")),
        output_tokens=_int_value(usage, ("output_tokens", "completion_tokens")),
        total_tokens=_int_value(usage, ("total_tokens",)),
    )


def _usage_from_raw_responses(result: Any) -> AgentRunUsage:
    raw_responses = _value(result, "raw_responses", []) or []
    usage = AgentRunUsage(
        request_count=len(raw_responses),
        model_response_count=len(raw_responses),
    )
    for response in raw_responses:
        response_usage = _value(response, "usage") or {}
        input_tokens = _int_value(response_usage, ("input_tokens", "prompt_tokens"))
        output_tokens = _int_value(
            response_usage,
            ("output_tokens", "completion_tokens"),
        )
        total_tokens = _int_value(response_usage, ("total_tokens",))
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.total_tokens += total_tokens or input_tokens + output_tokens
    return usage


def extract_run_usage(result: Any) -> AgentRunUsage:
    usage = _usage_from_context_wrapper(result)
    if usage.total_tokens or usage.input_tokens or usage.output_tokens:
        raw_response_count = len(_value(result, "raw_responses", []) or [])
        if usage.model_response_count == 0 and raw_response_count:
            usage.model_response_count = raw_response_count
        if usage.request_count == 0 and raw_response_count:
            usage.request_count = raw_response_count
        if usage.total_tokens == 0:
            usage.total_tokens = usage.input_tokens + usage.output_tokens
        return usage
    return _usage_from_raw_responses(result)


def extract_run_observations(result: Any) -> RunObservations:
    """Extract tool and handoff facts from a RunResult-like object.

    The OpenAI Agents SDK exposes rich `new_items`, but tests often use simple
    dicts or SimpleNamespace objects. This adapter intentionally accepts both.
    """

    observations = RunObservations()
    tool_name_by_call_id: dict[str, str] = {}
    previous_tool_name: str | None = None
    for item in _value(result, "new_items", []) or []:
        item_type = _item_type(item)
        agent = _agent_name(_value(item, "agent"))

        if item_type in {"tool_call_item", "ToolCallItem"}:
            tool_name = _tool_name(item)
            if tool_name:
                call_id = _tool_call_id(item)
                if call_id:
                    tool_name_by_call_id[call_id] = tool_name
                previous_tool_name = tool_name
                observations.tool_calls.append(
                    AgentToolCall(name=tool_name, status="called", agent=agent)
                )
            continue

        if item_type in {"tool_call_output_item", "ToolCallOutputItem"}:
            call_id = _tool_call_id(item)
            tool_name = (
                _tool_name(item)
                or (tool_name_by_call_id.get(call_id) if call_id else None)
                or previous_tool_name
            )
            validation = _specialist_output_validation(
                tool_name=tool_name,
                output_payload=_tool_output_payload(item),
            )
            if validation is not None:
                observations.output_validations.append(validation)
            continue

        if item_type in {"handoff_call_item", "HandoffCallItem"}:
            tool_name = _tool_name(item)
            target = _handoff_target_from_tool(tool_name)
            if agent and target:
                observations.handoffs.append(
                    AgentHandoff(
                        from_agent=agent,
                        to_agent=target,
                        status="planned",
                        reason="sdk_handoff_call",
                    )
                )
            continue

        if item_type in {"handoff_output_item", "HandoffOutputItem"}:
            source_agent = _agent_name(_value(item, "source_agent"))
            target_agent = _agent_name(_value(item, "target_agent"))
            if source_agent and target_agent:
                observations.handoffs.append(
                    AgentHandoff(
                        from_agent=source_agent,
                        to_agent=target_agent,
                        status="completed",
                        reason="sdk_handoff_output",
                    )
                )

    observations.tool_calls = _dedupe_tool_calls(observations.tool_calls)
    observations.handoffs = _dedupe_handoffs(observations.handoffs)
    observations.usage = extract_run_usage(result)
    return observations


class HarnessRunHooks:
    """SDK hook-compatible recorder for local tool timing and handoff events."""

    def __init__(self):
        self.observations = RunObservations()
        self._tool_starts: dict[tuple[str, str | None], float] = {}

    async def on_tool_start(self, context: Any, agent: Any, tool: Any) -> None:
        tool_name = _tool_context_name(context) or _tool_name(tool)
        if not tool_name:
            return
        agent_name = _agent_name(agent)
        self._tool_starts[(tool_name, agent_name)] = perf_counter()

    async def on_tool_end(
        self,
        context: Any,
        agent: Any,
        tool: Any,
        result: object,
    ) -> None:
        tool_name = _tool_context_name(context) or _tool_name(tool)
        if not tool_name:
            return
        agent_name = _agent_name(agent)
        started_at = self._tool_starts.pop((tool_name, agent_name), None)
        latency_ms = None
        if started_at is not None:
            latency_ms = round((perf_counter() - started_at) * 1000, 2)
        self.observations.tool_calls.append(
            AgentToolCall(
                name=tool_name,
                status="called",
                agent=agent_name,
                latency_ms=latency_ms,
            )
        )

    async def on_handoff(self, context: Any, from_agent: Any, to_agent: Any) -> None:
        from_name = _agent_name(from_agent)
        to_name = _agent_name(to_agent)
        if not from_name or not to_name:
            return
        self.observations.handoffs.append(
            AgentHandoff(
                from_agent=from_name,
                to_agent=to_name,
                status="completed",
                reason="sdk_run_hook",
            )
        )
