"""TurnContextualizer facade: deterministic first, model only for the
ambiguous remainder, always degrading safely to the deterministic result.

`contextualize_with_trace()` is the runtime entrypoint — it reports how
(and whether) the model was involved so the run ledger can account for
the LLM call. `contextualize()` remains the simple turn-only view.
"""

from __future__ import annotations

from datetime import date
from time import perf_counter
from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.runtime.orchestration.intake.contracts import (
    ContextualizedTurn,
    unchanged_turn,
)
from app.runtime.orchestration.intake.model_contextualizer import (
    ModelContextualizationResult,
    ModelTurnContextualizer,
)
from app.runtime.orchestration.intake.slot_resolver import SlotResolver
from app.runtime.orchestration.router.facts import MessageFacts

IntakeModelStatus = Literal[
    "skipped_deterministic",
    "skipped_model_unavailable",
    "called",
    "invalid_output",
    "failed",
]


class IntakeOutcome(BaseModel):
    """Contextualized turn plus the developer-layer account of the model call."""

    turn: ContextualizedTurn
    model_status: IntakeModelStatus = "skipped_deterministic"
    model_latency_ms: Optional[float] = None
    model_name: Optional[str] = None


def _normalize_model_result(result: Any) -> ModelContextualizationResult:
    """Tolerate legacy/fake contextualizers returning a turn or None."""

    if isinstance(result, ModelContextualizationResult):
        return result
    if isinstance(result, ContextualizedTurn):
        return ModelContextualizationResult(status="called", turn=result)
    return ModelContextualizationResult(status="failed")


class TurnContextualizer:
    """raw_message -> ContextualizedTurn. Never fails the chat request."""

    def __init__(self, model: ModelTurnContextualizer | None = None):
        self.slot_resolver = SlotResolver()
        self.model = model

    async def contextualize(
        self,
        raw_message: str,
        chat_history: list[dict[str, Any]] | None = None,
        memory_context: dict[str, Any] | None = None,
        *,
        today: date | None = None,
    ) -> ContextualizedTurn:
        outcome = await self.contextualize_with_trace(
            raw_message, chat_history, memory_context, today=today
        )
        return outcome.turn

    async def contextualize_with_trace(
        self,
        raw_message: str,
        chat_history: list[dict[str, Any]] | None = None,
        memory_context: dict[str, Any] | None = None,
        *,
        today: date | None = None,
    ) -> IntakeOutcome:
        facts = MessageFacts.from_message(raw_message, chat_history, memory_context)

        # High-certainty social turns are never rewritten ("OK", "哈哈").
        if facts.is_empty or (
            not facts.has_finance_signal
            and not facts.has_digits
            and (facts.is_exact_acknowledgement or facts.is_exact_greeting)
        ):
            return IntakeOutcome(turn=unchanged_turn(raw_message))

        turn = self.slot_resolver.resolve(
            raw_message, facts, memory_context, today=today
        )

        # Deterministic answer stands — never fabricate an LLM call record.
        if turn.resolution_status != "needs_clarification":
            return IntakeOutcome(turn=turn, model_status="skipped_deterministic")

        if self.model is None or not self.model.available():
            return IntakeOutcome(turn=turn, model_status="skipped_model_unavailable")

        started = perf_counter()
        result = _normalize_model_result(
            await self.model.contextualize(raw_message, chat_history, memory_context)
        )
        latency_ms = round((perf_counter() - started) * 1000, 2)

        if result.status == "called" and result.turn is not None:
            return IntakeOutcome(
                turn=result.turn,
                model_status="called",
                model_latency_ms=latency_ms,
                model_name=result.model_name,
            )
        return IntakeOutcome(
            turn=turn,
            model_status=result.status if result.status != "called" else "failed",
            model_latency_ms=latency_ms,
            model_name=result.model_name,
        )
