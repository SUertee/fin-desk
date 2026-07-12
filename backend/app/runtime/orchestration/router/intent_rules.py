"""Rule-based intent recognition: high-certainty shortcuts + offline fallback.

`classify()` handles ONLY provably-social shortcuts (empty message, exact
greetings, exact acknowledgements/filler) so the model owns finance
semantics. `fallback()` preserves the full v1 deterministic behavior for
when the model is unavailable or invalid — it is the reason the test suite
and offline evals run with zero LLM calls. Do not grow either into a
keyword router; new semantics belong in the classifier prompt + eval set.
"""

from __future__ import annotations

from app.runtime.orchestration.router.facts import MessageFacts
from app.runtime.orchestration.router.intent_types import IntentCandidate


def _rule(intent: str, reason_code: str) -> IntentCandidate:
    return IntentCandidate(
        intent=intent, confidence=1.0, reason_code=reason_code, source="rule"
    )


def _fallback(intent: str, reason_code: str) -> IntentCandidate:
    return IntentCandidate(
        intent=intent, confidence=0.0, reason_code=reason_code, source="fallback"
    )


class RuleIntentClassifier:
    """Deterministic intent recognition at two call points."""

    def classify(self, facts: MessageFacts) -> IntentCandidate | None:
        """High-certainty shortcuts; None sends the message to the model.

        Guarded by the absence of finance facts so a greeting-prefixed money
        question ("你好 帮我看下账单") can never short-circuit to small talk.
        """

        if facts.is_empty:
            return _rule("clarification", "empty_message")
        if facts.has_finance_signal or facts.has_digits:
            return None
        if facts.is_exact_acknowledgement:
            return _rule("acknowledgement", "exact_acknowledgement")
        if facts.is_exact_greeting:
            return _rule("small_talk", "exact_greeting")
        return None

    def fallback(self, facts: MessageFacts) -> IntentCandidate:
        """Deterministic v1 tail: full keyword routing, model-free.

        Ordering is load-bearing and mirrors v1 exactly: evidence →
        followup → finance → social shape → question → unsupported.
        """

        # Referring-back intents require PROVEN finance context (session
        # memory), not merely any prior assistant message — a capability
        # intro in history must not make "为什么这样建议" pretend citations
        # exist.
        if (
            facts.has_evidence_signal
            and not facts.has_finance_signal
            and not facts.has_digits
            and facts.has_prior_finance_context
        ):
            return _fallback("evidence_request", "evidence_signal")

        if (
            facts.has_prior_finance_context
            and facts.has_followup_signal
            and not facts.has_finance_signal
        ):
            return _fallback("finance_followup", "contextual_followup")

        if facts.has_finance_signal:
            if facts.has_prior_finance_context and facts.has_followup_signal:
                return _fallback("finance_followup", "finance_followup_signal")
            return _fallback("finance_question", "finance_signal")

        if facts.is_exact_acknowledgement:
            return _fallback("acknowledgement", "exact_acknowledgement")

        if facts.is_exact_greeting or facts.is_short_social_shape:
            return _fallback("small_talk", "social_shape")

        if facts.has_question_signal:
            return _fallback("clarification", "non_finance_question")

        return _fallback("unsupported", "no_recognizable_intent")
