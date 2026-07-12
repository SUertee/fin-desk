"""TurnContextualizer facade: deterministic first, model only for the
ambiguous remainder, always degrading safely to the deterministic result.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.runtime.orchestration.intake.contracts import (
    ContextualizedTurn,
    unchanged_turn,
)
from app.runtime.orchestration.intake.model_contextualizer import (
    ModelTurnContextualizer,
)
from app.runtime.orchestration.intake.slot_resolver import SlotResolver
from app.runtime.orchestration.router.facts import MessageFacts


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
        facts = MessageFacts.from_message(raw_message, chat_history, memory_context)

        # High-certainty social turns are never rewritten ("OK", "哈哈").
        if facts.is_empty or (
            not facts.has_finance_signal
            and not facts.has_digits
            and (facts.is_exact_acknowledgement or facts.is_exact_greeting)
        ):
            return unchanged_turn(raw_message)

        turn = self.slot_resolver.resolve(
            raw_message, facts, memory_context, today=today
        )

        if (
            turn.resolution_status == "needs_clarification"
            and self.model is not None
            and self.model.available()
        ):
            model_turn = await self.model.contextualize(
                raw_message, chat_history, memory_context
            )
            if model_turn is not None:
                return model_turn

        return turn
