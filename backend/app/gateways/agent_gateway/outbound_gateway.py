"""Outbound boundary for calling other personal agents from Finance."""

from __future__ import annotations

from app.gateways.agent_gateway.task_contracts import AgentTaskRequest


class OutboundAgentGateway:
    """Placeholder for future cross-agent delegation from the finance domain."""

    async def submit_task(self, target_agent: str, req: AgentTaskRequest) -> None:
        raise NotImplementedError(
            f"Outbound agent delegation is not configured for target_agent={target_agent}."
        )
