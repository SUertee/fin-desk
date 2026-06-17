"""Schemas for CFO-owned OpenAI agent output."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.agent_data import FinanceAgentData


class CFOAgentResult(BaseModel):
    reply: str
    data: FinanceAgentData | None = None
