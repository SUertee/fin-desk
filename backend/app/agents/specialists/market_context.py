"""Market Context specialist over preloaded, governed research evidence.

This agent module deliberately has no provider credentials, environment reads,
or HTTP client. Runtime tools own external access; the specialist only projects
typed evidence into the shared output contract.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistFinding,
    SpecialistInput,
)
from app.models.web_research import WebResearchResult


MAX_FINDINGS = 5
UNCERTAINTY_LIMITATION = (
    "Market information is time-sensitive and may be incomplete or already outdated."
)
NOT_ADVICE_LIMITATION = "Market context is informational, not financial advice."


def run(input: SpecialistInput) -> SpecialistAgentOutput:
    limitations = [UNCERTAINTY_LIMITATION, NOT_ADVICE_LIMITATION]
    raw = input.evidence.get("web_research")
    if not raw:
        return SpecialistAgentOutput(
            specialist="market_context",
            confidence=0.0,
            limitations=[
                "No governed web-research evidence was supplied by the runtime.",
                *limitations,
            ],
        )
    try:
        research = WebResearchResult.model_validate(raw)
    except ValidationError:
        return SpecialistAgentOutput(
            specialist="market_context",
            confidence=0.0,
            limitations=[
                "The supplied web-research evidence failed contract validation.",
                *limitations,
            ],
        )

    limitations.extend(research.limitations)
    if research.status == "unavailable":
        return SpecialistAgentOutput(
            specialist="market_context",
            confidence=0.0,
            limitations=limitations,
        )

    findings: list[SpecialistFinding] = []
    undated = 0
    for item in research.items[:MAX_FINDINGS]:
        timestamp = item.published_at or item.fetched_at
        if item.published_at is None:
            undated += 1
        evidence = [
            f"{item.domain}; {'published' if item.published_at else 'fetched'} {timestamp.isoformat()}"
        ]
        if item.snippet:
            evidence.append(item.snippet[:500])
        findings.append(
            SpecialistFinding(
                title=item.title,
                evidence=evidence,
                risk_level="low",
                source_url=item.url,
                published_at=(item.published_at.isoformat() if item.published_at else None),
            )
        )
    if undated:
        limitations.append(
            f"{undated} sources did not provide a publication timestamp; fetch time is shown instead."
        )
    if not findings:
        limitations.append("No governed market sources matched the query.")
    return SpecialistAgentOutput(
        specialist="market_context",
        confidence=0.55 if findings else 0.0,
        findings=findings,
        recommendations=[],
        limitations=limitations,
    )
