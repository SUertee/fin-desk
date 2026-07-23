"""My Office contracts: sessions, messages, and the user evidence projection.

The evidence projection is the USER layer of `trace-observability.md` — it
must never carry latency, usage, cost, model/provider names, confidence
values, or raw tool payloads. Those belong to the developer projection only.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.turn_execution import TurnExecutionFacts


class OfficeSession(BaseModel):
    id: str
    user_id: str
    title: str = ""
    status: Literal["active", "archived"] = "active"
    last_message_preview: str = ""
    created_at: str
    updated_at: str


class OfficeMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: str
    content: str
    request_id: Optional[str] = None
    execution: Optional[TurnExecutionFacts] = None
    created_at: str


class CreateSessionRequest(BaseModel):
    user_id: str = "demo"
    title: str = ""


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[Literal["active", "archived"]] = None


class EvidenceStep(BaseModel):
    label: str
    kind: Literal["tool", "specialist", "audit"]
    done: bool = True


class EvidenceFinding(BaseModel):
    agent: str
    title: str
    evidence: list[str] = Field(default_factory=list)


class DataCoverage(BaseModel):
    period: Optional[str] = None
    source_counts: dict[str, int] = Field(default_factory=dict)
    quality_warnings: list[str] = Field(default_factory=list)


class EvidenceAudit(BaseModel):
    status: str
    warnings: list[str] = Field(default_factory=list)


class AdvancedDetails(BaseModel):
    run_id: str
    tool_names: list[str] = Field(default_factory=list)


class UserEvidenceProjection(BaseModel):
    request_id: str
    findings: list[EvidenceFinding] = Field(default_factory=list)
    cited_sources: list[str] = Field(default_factory=list)
    data_coverage: DataCoverage = Field(default_factory=DataCoverage)
    steps: list[EvidenceStep] = Field(default_factory=list)
    audit: Optional[EvidenceAudit] = None
    advanced: Optional[AdvancedDetails] = None
