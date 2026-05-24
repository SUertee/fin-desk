"""
Chat-related Pydantic models: request and response.
"""

from typing import Optional

from pydantic import BaseModel

from models.agent_data import FinanceAgentData


class ChatRequest(BaseModel):
    message: str
    user_id: str = "demo"


class ChatResponse(BaseModel):
    reply: str
    agent_used: Optional[str] = None
    data: Optional[FinanceAgentData] = None
