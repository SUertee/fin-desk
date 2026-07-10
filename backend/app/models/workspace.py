"""Workspace brief contract shared with the web client."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.agent_data import AgentAction, AgentAudit, SummaryCard


class BriefPeriod(BaseModel):
    date_from: str = Field(alias="from")
    date_to: str = Field(alias="to")

    model_config = {"populate_by_name": True}


class WorkspaceBrief(BaseModel):
    """Agent-produced brief that drives the Action Center and Ask CFO panel.

    ``has_data=False`` is the typed empty state (no fabricated metrics) that
    the client must distinguish from an error response.
    """

    request_id: Optional[str] = None
    generated_at: str
    has_data: bool
    # The CFO's one-sentence judgment (composed reply) — the hero headline.
    headline: str = ""
    period: Optional[BriefPeriod] = None
    summary_cards: list[SummaryCard] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    audit: Optional[AgentAudit] = None
