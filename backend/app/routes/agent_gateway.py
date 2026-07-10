"""Routes for external agent interoperability."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.gateways.agent_gateway.agent_profile import build_finance_agent_profile
from app.gateways.agent_gateway.inbound_gateway import InboundAgentGateway
from app.gateways.agent_gateway.task_contracts import (
    AgentProfile,
    AgentTaskRequest,
    AgentTaskResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent-gateway", tags=["agent-gateway"])
_gateway = InboundAgentGateway()


@router.get("/profile", response_model=AgentProfile)
def get_agent_profile() -> AgentProfile:
    return build_finance_agent_profile()


@router.post("/tasks", response_model=AgentTaskResponse)
async def submit_agent_task(req: AgentTaskRequest):
    response = await _gateway.submit_task(req)
    if not response.ok:
        logger.warning(
            "Agent gateway task failed task_id=%s capability=%s",
            response.task_id,
            response.capability,
        )
        return JSONResponse(status_code=500, content=response.model_dump(mode="json"))
    return response


@router.get("/tasks/{task_id}", response_model=AgentTaskResponse)
def get_agent_task(task_id: str):
    response = _gateway.get_task(task_id)
    if response is None:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": "Agent gateway task not found"},
        )
    return response
