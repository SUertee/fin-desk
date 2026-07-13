"""Route resolution: the ONLY place an execution path is decided.

Takes a semantic `IntentCandidate` plus `MessageFacts` and produces the
unchanged public `ConversationRoute`. Corrections use verifiable facts and
a single low-confidence rule — never model output beyond the intent enum.
The audit trail (guard reason, candidate, bounded excerpt) is developer
observability only and never reaches the product UI.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.models.routing import ConversationRoute, route_for_path
from app.models.runtime import AgentRunUsage
from app.runtime.orchestration.router.facts import MessageFacts
from app.runtime.orchestration.router.intent_types import IntentCandidate

# Below this, a model verdict alone is not enough to start a pipeline run;
# verifiable finance facts can still escalate (mirrors the yili threshold).
LOW_CONFIDENCE_THRESHOLD = 0.5

GuardReason = Literal[
    "rule_decisive",
    "fallback_decisive",
    "model_accepted",
    "lexical_finance_override",
    "no_context_downgrade",
    "low_confidence_downgrade",
]

ClassifierCallStatus = Literal["skipped", "called", "invalid_output", "failed"]

# How each internal intent executes.
_INTENT_TO_PATH: dict[str, str] = {
    "small_talk": "light_reply",
    "acknowledgement": "light_reply",
    "capability_question": "light_reply",
    "finance_question": "cfo_analysis",
    "finance_followup": "cfo_followup",
    "evidence_request": "evidence_only",
    "clarification": "clarification",
    "unsupported": "clarification",
}

# Internal semantic vocabulary -> unchanged public ConversationIntent.
_INTERNAL_TO_PUBLIC_INTENT: dict[str, str] = {
    "small_talk": "small_talk",
    "acknowledgement": "acknowledgement",
    "capability_question": "small_talk",
    "finance_question": "finance_query",
    "finance_followup": "follow_up",
    "evidence_request": "evidence_request",
    "clarification": "clarification",
    "unsupported": "unsupported",
}

_LIGHT_INTENTS = {
    "small_talk",
    "acknowledgement",
    "capability_question",
    "clarification",
    "unsupported",
}

_PIPELINE_INTENTS = {"finance_question", "finance_followup", "evidence_request"}


class RouteDecision(BaseModel):
    """Final routing outcome plus the audit trail for the run ledger."""

    route: ConversationRoute
    candidate: IntentCandidate
    guard_reason: GuardReason
    message_excerpt: str
    classifier_status: ClassifierCallStatus = "skipped"
    classifier_latency_ms: float | None = None
    # Billing facts for the classifier call (developer layer only).
    classifier_usage: "AgentRunUsage | None" = None
    classifier_model: str | None = None

    def ledger_dump(self) -> dict:
        """Developer-layer projection: bounded excerpt, candidate, guard call."""

        return {
            "message_excerpt": self.message_excerpt,
            "candidate": self.candidate.model_dump(),
            "guard_reason": self.guard_reason,
            "classifier_status": self.classifier_status,
        }


class RouteResolver:
    """intent + facts -> execution path -> ConversationRoute."""

    def resolve(
        self, candidate: IntentCandidate, facts: MessageFacts
    ) -> tuple[ConversationRoute, GuardReason]:
        intent = candidate.intent
        reason: GuardReason = (
            "model_accepted" if candidate.source == "model" else f"{candidate.source}_decisive"  # type: ignore[assignment]
        )

        # Corrections apply to model verdicts only: rule and fallback
        # candidates are fact-derived by construction.
        if candidate.source == "model":
            finance_facts = facts.has_finance_signal or facts.has_digits

            # Model undercalled a message carrying verifiable finance facts.
            if intent in _LIGHT_INTENTS and finance_facts:
                intent, reason = "finance_question", "lexical_finance_override"

            # Referring-back intents need something real to refer to.
            elif intent == "evidence_request" and not facts.has_prior_finance_context:
                intent, reason = "clarification", "no_context_downgrade"
            elif intent == "finance_followup" and not facts.has_prior_finance_context:
                intent, reason = "clarification", "no_context_downgrade"

            # An unconfident model verdict alone must not start a pipeline
            # run; verifiable finance facts may (asymmetric escalation).
            elif (
                intent in _PIPELINE_INTENTS
                and candidate.confidence < LOW_CONFIDENCE_THRESHOLD
                and not finance_facts
            ):
                intent, reason = "clarification", "low_confidence_downgrade"

        route = route_for_path(
            _INTERNAL_TO_PUBLIC_INTENT[intent],
            _INTENT_TO_PATH[intent],
            label=candidate.reason_code or reason,
        )
        return route, reason
