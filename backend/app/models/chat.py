"""
Chat-related Pydantic models: request and response.
"""

from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.agent_data import FinanceAgentData, normalize_finance_agent_data


class ChatRequest(BaseModel):
    message: str
    user_id: str = "demo"


class ChatResponse(BaseModel):
    reply: str
    agent_used: Optional[str] = None
    data: Optional[FinanceAgentData] = None

    @field_validator("data", mode="before")
    @classmethod
    def normalize_agent_data(cls, value: object) -> FinanceAgentData | None:
        return normalize_finance_agent_data(value)
