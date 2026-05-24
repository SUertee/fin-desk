"""
Structured data returned by the finance agent team.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


SummaryStatus = Literal["neutral", "good", "watch", "risk"]
EffortLevel = Literal["low", "medium", "high"]
ImpactLevel = Literal["low", "medium", "high"]
AuditStatus = Literal["verified", "needs_review", "data_limited"]


class SummaryCard(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    value: str
    status: SummaryStatus = "neutral"
    note: str | None = None


class AgentFinding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent: str
    title: str
    evidence: list[str] = Field(default_factory=list)


class AgentAction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    rationale: str
    effort: EffortLevel
    impact: ImpactLevel


class AgentAudit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confidence: float = Field(ge=0.0, le=1.0)
    status: AuditStatus
    warnings: list[str] = Field(default_factory=list)


class FinanceAgentData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary_cards: list[SummaryCard] | None = None
    findings: list[AgentFinding] | None = None
    actions: list[AgentAction] | None = None
    audit: AgentAudit | None = None


def _normalize_list(model: type[BaseModel], value: object) -> list[BaseModel] | None:
    if not isinstance(value, list):
        return None

    items: list[BaseModel] = []
    for raw_item in value:
        try:
            items.append(model.model_validate(raw_item))
        except ValidationError:
            continue

    return items or None


def normalize_finance_agent_data(value: object) -> FinanceAgentData | None:
    if isinstance(value, FinanceAgentData):
        return value
    if not isinstance(value, dict):
        return None

    audit = None
    try:
        audit = AgentAudit.model_validate(value.get("audit"))
    except ValidationError:
        audit = None

    normalized = FinanceAgentData(
        summary_cards=_normalize_list(SummaryCard, value.get("summary_cards")),
        findings=_normalize_list(AgentFinding, value.get("findings")),
        actions=_normalize_list(AgentAction, value.get("actions")),
        audit=audit,
    )

    if not any(
        [
            normalized.summary_cards,
            normalized.findings,
            normalized.actions,
            normalized.audit,
        ]
    ):
        return None

    return normalized
