"""Entry routing package: semantic intent recognition, deterministic
route resolution.

Layering (see openspec change `entry-router-v2`):

- semantic layer proposes WHAT the user means: `RuleIntentClassifier`
  (shortcuts + fallback) and `ModelIntentClassifier` both emit
  `IntentCandidate` — never an execution path.
- execution layer decides HOW it runs: `RouteResolver` alone maps intent
  + `MessageFacts` onto the unchanged public `ConversationRoute`.
"""

from app.runtime.orchestration.router.entry import EntryRouter
from app.runtime.orchestration.router.facts import MessageFacts
from app.runtime.orchestration.router.intent_model import ModelIntentClassifier
from app.runtime.orchestration.router.intent_rules import RuleIntentClassifier
from app.runtime.orchestration.router.intent_types import (
    ClassifierInput,
    IntentCandidate,
    IntentClassifier,
    build_classifier_input,
)
from app.runtime.orchestration.router.resolver import (
    RouteDecision,
    RouteResolver,
)

__all__ = [
    "ClassifierInput",
    "EntryRouter",
    "IntentCandidate",
    "IntentClassifier",
    "MessageFacts",
    "ModelIntentClassifier",
    "RouteDecision",
    "RouteResolver",
    "RuleIntentClassifier",
    "build_classifier_input",
]
