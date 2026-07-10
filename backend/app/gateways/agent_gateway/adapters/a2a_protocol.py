"""A2A protocol mapping helpers for the agent gateway.

This module deliberately keeps A2A-specific naming out of the application
package structure. The current implementation exposes a lightweight card shape;
full A2A server concerns such as streaming and push notifications can be added
here without changing the internal FinanceRuntime.
"""

from __future__ import annotations

from typing import Any

from app.gateways.agent_gateway.task_contracts import AgentProfile, AgentTaskRequest


def to_a2a_agent_card(profile: AgentProfile) -> dict[str, Any]:
    return {
        "id": profile.agent_id,
        "name": profile.name,
        "description": profile.description,
        "version": profile.version,
        "capabilities": [
            {
                "name": capability.name,
                "description": capability.description,
                "inputContract": capability.input_contract,
                "outputContract": capability.output_contract,
            }
            for capability in profile.capabilities
        ],
    }


def from_a2a_task_message(payload: dict[str, Any]) -> AgentTaskRequest:
    return AgentTaskRequest(
        task_id=payload.get("taskId"),
        user_id=payload.get("userId") or "demo",
        requester_agent=payload.get("requesterAgent"),
        capability=payload.get("capability"),
        message=payload.get("message") or "",
        context=payload.get("context") or {},
        correlation_id=payload.get("correlationId"),
    )
