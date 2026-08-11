"""Typed CFO decision boundary between conversation and execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.models.runtime import AgentRunUsage
from app.runtime.capabilities.contracts import CapabilityDescriptor


CfoTurnAction = Literal["direct_response", "ask_clarification", "execute"]
CfoDecisionStatus = Literal["called", "unavailable", "invalid_output", "failed"]


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    capability_id: str = Field(min_length=3, max_length=100)


class CfoTurnDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: CfoTurnAction
    reply: str | None = Field(default=None, max_length=2000)
    capability_requests: list[CapabilityRequest] = Field(
        default_factory=list,
        max_length=8,
    )

    @model_validator(mode="after")
    def validate_action_payload(self) -> "CfoTurnDecision":
        reply = (self.reply or "").strip()
        if self.action in {"direct_response", "ask_clarification"}:
            if not reply:
                raise ValueError("A conversational action requires a reply")
            if self.capability_requests:
                raise ValueError("A conversational action cannot request capabilities")
        elif not self.capability_requests:
            raise ValueError("Execute requires at least one capability")
        elif reply:
            raise ValueError("Execute cannot contain a final reply")
        return self


@dataclass(frozen=True)
class CfoDecisionResult:
    status: CfoDecisionStatus
    decision: CfoTurnDecision | None = None
    usage: AgentRunUsage = field(default_factory=AgentRunUsage)
    model_name: str | None = None
    latency_ms: float | None = None


class CfoDecisionEngine:
    """Ask the CFO model for an action, never an execution implementation."""

    def __init__(self, client_getter: Callable[[], Any]):
        self._client_getter = client_getter

    async def decide(
        self,
        message: str,
        *,
        capabilities: tuple[CapabilityDescriptor, ...],
        chat_history: list[dict[str, Any]],
        memory_context: dict[str, Any],
        profile: dict[str, Any],
        needs_clarification: bool,
    ) -> CfoDecisionResult:
        client = self._client_getter()
        if client is None or not getattr(client, "available", lambda *_: False)(
            "router"
        ):
            return CfoDecisionResult(status="unavailable")

        started = perf_counter()
        try:
            response = await client.generate_json(
                self._prompt(
                    message,
                    capabilities=capabilities,
                    chat_history=chat_history,
                    memory_context=memory_context,
                    profile=profile,
                    needs_clarification=needs_clarification,
                ),
                profile="router",
                system=self._system_prompt(),
            )
        except Exception:
            return CfoDecisionResult(
                status="failed",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

        latency_ms = round((perf_counter() - started) * 1000, 2)
        usage = getattr(response, "usage", AgentRunUsage())
        model_name = getattr(response, "model_name", None)
        try:
            decision = CfoTurnDecision.model_validate(response.data)
            allowlist = {item.capability_id for item in capabilities}
            requested = {
                item.capability_id for item in decision.capability_requests
            }
            if not requested <= allowlist:
                raise ValueError("Decision requested a capability outside the catalog")
        except (ValidationError, ValueError, TypeError):
            return CfoDecisionResult(
                status="invalid_output",
                usage=usage,
                model_name=model_name,
                latency_ms=latency_ms,
            )
        return CfoDecisionResult(
            status="called",
            decision=decision,
            usage=usage,
            model_name=model_name,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are the lead CFO in a personal finance workspace. Decide the next "
            "action from the user's meaning and bounded conversation context. Return "
            "strict JSON only with action, reply, and capability_requests. Use "
            "direct_response for greetings, acknowledgements, capability questions, "
            "and general conversation that makes no factual claim about the user's "
            "finances or external markets. Any answer about transactions, spending, "
            "income, cash flow, budgets, anomalies, financial history, market data, "
            "amounts, or percentages must use execute to obtain registered evidence, "
            "even when related figures appear in conversation history or memory. "
            "Conversation context may resolve meaning but is never evidence. Any "
            "answer about the user's uploaded documents (PDFs, images, research "
            "notes, or anything the user attached) must use the knowledge.user_search "
            "capability to retrieve evidence from those documents; image hits include "
            "a preview URL you can surface to the user. Use "
            "ask_clarification when a safe answer requires missing information. For "
            "execute, reply must be null and capability_requests must contain "
            "capability_id objects. Never "
            "output providers, tool names, SQL, permissions, execution paths, UI flags, "
            "hidden reasoning, or capabilities absent from the supplied catalog. Reply "
            "in the user's language."
        )

    @staticmethod
    def _prompt(
        message: str,
        *,
        capabilities: tuple[CapabilityDescriptor, ...],
        chat_history: list[dict[str, Any]],
        memory_context: dict[str, Any],
        profile: dict[str, Any],
        needs_clarification: bool,
    ) -> str:
        recent = [
            {
                "role": str(item.get("role") or "")[:20],
                "content": str(item.get("content") or "")[:300],
            }
            for item in chat_history[-6:]
        ]
        session_memory = memory_context.get("session_memory") or {}
        preferences = profile.get("preferences") or {}
        payload = {
            "message": message[:2000],
            "context_resolution_requires_clarification": needs_clarification,
            "recent_conversation": recent,
            "session_summary": str(session_memory.get("conversation_summary") or "")[:800],
            "last_topic": session_memory.get("last_topic"),
            "user_preferences": {
                "language": preferences.get("language"),
                "response_tone": preferences.get("response_tone"),
            },
            "capabilities": [
                {
                    "capability_id": item.capability_id,
                    "kind": item.kind,
                    "title": item.title,
                    "description": item.description,
                    "risk_level": item.risk_level,
                }
                for item in capabilities
            ],
            "response_schema": {
                "action": "direct_response | ask_clarification | execute",
                "reply": "string | null",
                "capability_requests": [{"capability_id": "registered.id"}],
            },
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
