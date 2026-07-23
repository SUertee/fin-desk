"""
Chat-related Pydantic models: request and response.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.agent_data import FinanceAgentData, normalize_finance_agent_data
from app.models.turn_execution import TurnExecutionFacts


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    user_id: str = "demo"
    # My Office session; empty/None uses the default chat scope.
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str
    agent_used: Optional[str] = None
    request_id: Optional[str] = None
    data: Optional[FinanceAgentData] = None
    execution: TurnExecutionFacts

    @field_validator("data", mode="before")
    @classmethod
    def normalize_agent_data(cls, value: object) -> FinanceAgentData | None:
        return normalize_finance_agent_data(value)
