"""EntryRouter facade: facts -> intent recognition -> route resolution.

Pipeline per turn:

    MessageFacts.from_message()          derive facts once
      -> RuleIntentClassifier.classify() high-certainty social shortcuts
      -> ModelIntentClassifier.classify() semantic intent (ambiguous band)
      -> RuleIntentClassifier.fallback()  deterministic v1 tail
      -> RouteResolver.resolve()          the only execution-path decision

`route()` is the fully deterministic synchronous path (shortcuts +
fallback, zero LLM) used by tests and offline evals. `decide()` is the
runtime entrypoint; with no classifier configured it is behaviorally
identical to `route()`.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from app.models.routing import ConversationRoute
from app.runtime.orchestration.router.facts import MessageFacts, excerpt
from app.runtime.orchestration.router.intent_rules import RuleIntentClassifier
from app.runtime.orchestration.router.intent_types import (
    IntentClassifier,
    build_classifier_input,
)
from app.runtime.orchestration.router.resolver import (
    ClassifierCallStatus,
    RouteDecision,
    RouteResolver,
)


def _normalize_classification(raw: Any) -> "IntentClassification":
    """Tolerate legacy/fake classifiers returning a candidate or None."""

    from app.runtime.orchestration.router.intent_model import IntentClassification
    from app.runtime.orchestration.router.intent_types import IntentCandidate

    if isinstance(raw, IntentClassification):
        return raw
    if isinstance(raw, IntentCandidate):
        return IntentClassification(status="called", candidate=raw)
    return IntentClassification(status="failed")


class EntryRouter:
    """Hybrid entry router with a deterministic spine."""

    def __init__(self, classifier: IntentClassifier | None = None):
        self.rules = RuleIntentClassifier()
        self.resolver = RouteResolver()
        self.classifier = classifier

    def route(
        self,
        message: str,
        *,
        chat_history: list[dict[str, Any]] | None = None,
        memory_context: dict[str, Any] | None = None,
    ) -> ConversationRoute:
        facts = MessageFacts.from_message(message, chat_history, memory_context)
        candidate = self.rules.classify(facts) or self.rules.fallback(facts)
        route, _ = self.resolver.resolve(candidate, facts)
        return route

    async def decide(
        self,
        message: str,
        *,
        chat_history: list[dict[str, Any]] | None = None,
        memory_context: dict[str, Any] | None = None,
    ) -> RouteDecision:
        facts = MessageFacts.from_message(message, chat_history, memory_context)
        candidate = self.rules.classify(facts)

        classifier_status: ClassifierCallStatus = "skipped"
        classifier_latency_ms: float | None = None
        classifier_usage = None
        classifier_model: str | None = None
        if candidate is None and self.classifier is not None and self.classifier.available():
            payload = build_classifier_input(
                message, facts, chat_history, memory_context
            )
            started = perf_counter()
            raw_result = await self.classifier.classify(payload)
            classifier_latency_ms = round((perf_counter() - started) * 1000, 2)
            classification = _normalize_classification(raw_result)
            classifier_usage = classification.usage
            classifier_model = classification.model_name
            if classification.candidate is not None:
                candidate = classification.candidate
                classifier_status = "called"
            else:
                classifier_status = classification.status

        if candidate is None:
            candidate = self.rules.fallback(facts)

        route, guard_reason = self.resolver.resolve(candidate, facts)
        return RouteDecision(
            route=route,
            candidate=candidate,
            guard_reason=guard_reason,
            message_excerpt=excerpt(message),
            classifier_status=classifier_status,
            classifier_latency_ms=classifier_latency_ms,
            classifier_usage=classifier_usage,
            classifier_model=classifier_model,
        )
