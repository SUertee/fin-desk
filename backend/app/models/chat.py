"""
Chat-related Pydantic models: request and response.
"""

from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.agent_data import FinanceAgentData, normalize_finance_agent_data
from app.models.routing import ConversationRoute


class ChatRequest(BaseModel):
    message: str
    user_id: str = "demo"
    # Typed routing hint: adds the named specialist to the selection set;
    # never removes policy-selected specialists or bypasses audit gating.
    requested_specialist: Optional[str] = None
    # My Office session; empty/None keeps the legacy flat history.
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    agent_used: Optional[str] = None
    request_id: Optional[str] = None
    data: Optional[FinanceAgentData] = None
    route: Optional[ConversationRoute] = None

    @field_validator("data", mode="before")
    @classmethod
    def normalize_agent_data(cls, value: object) -> FinanceAgentData | None:
        return normalize_finance_agent_data(value)
