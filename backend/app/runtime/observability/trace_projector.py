"""Project raw agent run records into UI-friendly observability sections."""

from __future__ import annotations

from typing import Any

from app.models.runtime import AgentRunRecord


def project_run_record(record: AgentRunRecord | dict[str, Any]) -> dict[str, Any]:
    run = AgentRunRecord.model_validate(record)
    timeline = [
        {
            "kind": "agent_selected",
            "label": agent,
            "status": "selected",
            "agent": agent,
        }
        for agent in run.selected_agents
    ]
    timeline.extend(
        {
            "kind": "tool_call",
            "label": tool.name,
            "status": tool.status,
            "agent": tool.agent,
            "latency_ms": tool.latency_ms,
        }
        for tool in run.tool_calls
    )
    timeline.extend(
        {
            "kind": "handoff",
            "label": f"{handoff.from_agent} -> {handoff.to_agent}",
            "status": handoff.status,
            "reason": handoff.reason,
        }
        for handoff in run.handoffs
    )
    timeline.extend(
        {
            "kind": "validation",
            "label": f"{validation.agent}.{validation.contract}",
            "status": validation.status,
            "errors": validation.errors,
        }
        for validation in run.output_validations
    )

    return {
        "summary": {
            "request_id": run.request_id,
            "entrypoint": run.entrypoint,
            "user_id": run.user_id,
            "runtime_requested": run.runtime_requested,
            "runtime_used": run.runtime_used,
            "model_name": run.model_name,
            "selected_agents": run.selected_agents,
            "output_contract": run.output_contract,
            "audit_status": run.audit_status,
            "latency_ms": run.latency_ms,
            "error_type": run.error_type,
        },
        "timeline": timeline,
        "tools": [tool.model_dump(mode="json") for tool in run.tool_calls],
        "handoffs": [handoff.model_dump(mode="json") for handoff in run.handoffs],
        "validations": [
            validation.model_dump(mode="json") for validation in run.output_validations
        ],
        "usage": run.usage.model_dump(mode="json"),
        "cost": run.cost.model_dump(mode="json"),
        "policy": run.policy,
        "input_summary": run.input_summary.model_dump(mode="json"),
        "raw": run.model_dump(mode="json"),
    }
