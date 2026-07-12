"""Internal semantic-layer types for entry routing.

`IntentCandidate` deliberately has NO execution_path: the model (and rule
shortcuts) only ever propose WHAT the user means; `RouteResolver` alone
decides HOW it executes. These types are developer-layer — nothing here is
returned to the product UI.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.runtime.orchestration.router.facts import MessageFacts

# Semantic vocabulary (internal). Wider than the public ConversationIntent;
# the resolver maps it back onto the unchanged public contract.
IntentName = Literal[
    "small_talk",
    "acknowledgement",
    "capability_question",
    "finance_question",
    "finance_followup",
    "evidence_request",
    "clarification",
    "unsupported",
]

IntentSource = Literal["rule", "model", "fallback"]


class IntentCandidate(BaseModel):
    """A semantic proposal: what the user means, never how it executes."""

    intent: IntentName
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_code: str = ""
    source: IntentSource = "rule"


class ClassifierInput(BaseModel):
    """Bounded context handed to the model classifier.

    Data minimization: truncated excerpts only — no full history, no
    profile, no amounts beyond what the excerpts naturally carry (the same
    provider already sees the evidence digest at compose time).
    """

    message: str
    facts: MessageFacts
    recent_turns: list[dict[str, str]] = Field(default_factory=list)
    last_topic_focus: str | None = None
    last_cfo_brief: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class IntentClassifier(Protocol):
    """Injected semantic classifier for the non-shortcut band."""

    def available(self) -> bool: ...

    async def classify(self, payload: ClassifierInput) -> IntentCandidate | None: ...


def build_classifier_input(
    message: str,
    facts: MessageFacts,
    chat_history: list[dict[str, Any]] | None = None,
    memory_context: dict[str, Any] | None = None,
    *,
    max_turns: int = 4,
    turn_excerpt: int = 80,
    brief_excerpt: int = 100,
) -> ClassifierInput:
    from app.runtime.orchestration.router.facts import excerpt

    history = chat_history or []
    recent_turns = [
        {
            "role": str(turn.get("role") or ""),
            "content": excerpt(str(turn.get("content") or ""), turn_excerpt),
        }
        for turn in history[-max_turns:]
        if turn.get("content")
    ]
    session_memory = (memory_context or {}).get("session_memory") or {}
    last_topic = session_memory.get("last_topic") or {}
    last_topic_focus = str(last_topic.get("focus") or "") or None
    last_cfo_brief = (
        excerpt(str(session_memory.get("last_result_brief") or ""), brief_excerpt)
        or None
    )
    if last_cfo_brief is None:
        for turn in reversed(history):
            if str(turn.get("role")) == "assistant" and turn.get("content"):
                last_cfo_brief = excerpt(str(turn["content"]), brief_excerpt)
                break
    return ClassifierInput(
        message=message,
        facts=facts,
        recent_turns=recent_turns,
        last_topic_focus=last_topic_focus,
        last_cfo_brief=last_cfo_brief,
    )
