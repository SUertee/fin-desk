"""Protocol-neutral gateway for external agent interoperability."""

from app.gateways.agent_gateway.agent_profile import build_finance_agent_profile
from app.gateways.agent_gateway.inbound_gateway import InboundAgentGateway
from app.gateways.agent_gateway.task_contracts import (
    AgentTaskRequest,
    AgentTaskResponse,
)

__all__ = [
    "AgentTaskRequest",
    "AgentTaskResponse",
    "InboundAgentGateway",
    "build_finance_agent_profile",
]
