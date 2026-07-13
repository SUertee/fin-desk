"""Turn intake: contextualize a raw chat turn before routing.

The intake layer answers "what does this turn refer to?" — the router
answers "what is the intent?" and the resolver answers "how to execute".
Raw user text is preserved for history/UI; `effective_message` feeds
routing, policy, planning, and tools.
"""

from app.runtime.orchestration.intake.contextualizer import (
    IntakeOutcome,
    TurnContextualizer,
)
from app.runtime.orchestration.intake.contracts import (
    ContextualizedTurn,
    ResolvedSlot,
    unchanged_turn,
)
from app.runtime.orchestration.intake.model_contextualizer import (
    ModelContextualizationResult,
    ModelTurnContextualizer,
)
from app.runtime.orchestration.intake.slot_resolver import SlotResolver

__all__ = [
    "ContextualizedTurn",
    "IntakeOutcome",
    "ModelContextualizationResult",
    "ModelTurnContextualizer",
    "ResolvedSlot",
    "SlotResolver",
    "TurnContextualizer",
    "unchanged_turn",
]
