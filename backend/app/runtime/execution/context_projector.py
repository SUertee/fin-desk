"""Specialist-specific evidence projection from CFO-owned run context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.runtime.execution.artifact_registry import ArtifactRegistry


@dataclass(frozen=True)
class ProjectedContext:
    evidence: dict[str, Any]
    artifact_refs: tuple[str, ...]


_PROJECTIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "expense_analyst": {
        "expense_snapshot": ("get_expense_snapshot",),
        "import_quality": ("get_import_quality_report",),
    },
    "budget_coach": {
        "budget_snapshot": ("get_budget_snapshot",),
    },
    "market_context": {
        "web_research": ("search_web_research",),
    },
    "investment_research": {
        "investment_research": (
            "get_vibe_market_data",
            "get_investment_research_context",
        ),
    },
    "auditor": {
        "transaction_evidence_available": ("get_finance_context",),
        "investment_research": (
            "get_vibe_market_data",
            "get_investment_research_context",
        ),
    },
}


class ContextProjector:
    """Build a minimal evidence view for one registered specialist."""

    def project(
        self,
        specialist: str,
        *,
        finance_context: dict[str, Any],
        artifacts: ArtifactRegistry,
    ) -> ProjectedContext:
        projection = _PROJECTIONS.get(specialist)
        if projection is None:
            raise ValueError(f"No context projection registered for {specialist}")

        evidence: dict[str, Any] = {
            "reply_language": finance_context.get("reply_language", "en")
        }
        refs: list[str] = []
        for context_key, producers in projection.items():
            producer = next(
                (name for name in producers if artifacts.get(name) is not None),
                None,
            )
            if producer is None:
                continue
            if context_key == "transaction_evidence_available":
                value = bool(finance_context.get("transactions_sample"))
            elif context_key not in finance_context:
                continue
            else:
                value = finance_context[context_key]
            evidence[context_key] = value
            refs.append(f"artifact://{producer}")

        return ProjectedContext(
            evidence=evidence,
            artifact_refs=tuple(dict.fromkeys(refs)),
        )
