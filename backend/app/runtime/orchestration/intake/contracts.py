"""Turn-intake contracts: the auditable result of contextualizing one turn.

`effective_message` is an INTERNAL execution input — routing, policy,
planning, and tools read it. The user's raw text is preserved untouched
for chat history and UI. Nothing in these contracts selects tools,
specialists, execution paths, SQL, fields, or filters.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SlotType = Literal[
    "date",
    "date_range",
    "category",
    "merchant",
    "transaction",
    "topic",
    "metric",
    "direction",
]

SlotSource = Literal[
    "raw_message",
    "session_memory",
    "recent_turn",
    "last_query",
    "model",
]

ResolutionStatus = Literal["unchanged", "resolved", "needs_clarification"]


class ResolvedSlot(BaseModel):
    slot_type: SlotType
    value: str
    source: SlotSource
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_text: Optional[str] = None


class ContextualizedTurn(BaseModel):
    raw_message: str
    effective_message: str
    rewrite_applied: bool = False
    resolution_status: ResolutionStatus = "unchanged"
    resolved_slots: list[ResolvedSlot] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    ambiguity_reason: str = ""

    def ledger_dump(self) -> dict:
        """Developer-layer projection — bounded, no chat history, no prompts."""

        return {
            "resolution_status": self.resolution_status,
            "rewrite_applied": self.rewrite_applied,
            "confidence": self.confidence,
            "ambiguity_reason": self.ambiguity_reason,
            "resolved_slots": [
                {
                    "slot_type": slot.slot_type,
                    "value": slot.value,
                    "source": slot.source,
                    "confidence": slot.confidence,
                }
                for slot in self.resolved_slots
            ],
        }


def unchanged_turn(raw_message: str) -> ContextualizedTurn:
    return ContextualizedTurn(
        raw_message=raw_message,
        effective_message=raw_message,
        rewrite_applied=False,
        resolution_status="unchanged",
    )
