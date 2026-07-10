"""Market Context specialist (policy-gated).

Provides external market/news facts as evidence for the CFO. Output
discipline is enforced structurally, not by prompt:

- every externally grounded finding must carry ``source_url`` and
  ``published_at`` — articles lacking either are dropped;
- ``limitations`` always includes an uncertainty statement and a
  not-financial-advice statement;
- when news is not configured, the output is a typed "unavailable" result —
  never fabricated headlines.

The runtime only reaches this specialist when runtime policy selected it
(market intent AND the MARKET_CONTEXT_ENABLED gate).
"""

from __future__ import annotations

import os
from typing import Any

from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistFinding,
    SpecialistInput,
)

NEWS_API_BASE = "https://newsapi.org/v2"
MAX_ARTICLES = 5

UNCERTAINTY_LIMITATION = (
    "Market information is time-sensitive and may be incomplete or already outdated."
)
NOT_ADVICE_LIMITATION = "Market context is informational, not financial advice."


def _fetch_articles(query: str) -> list[dict[str, Any]]:
    """Synchronous news fetch; isolated so tests and offline evals fake it."""

    import httpx

    api_key = os.getenv("NEWS_API_KEY", "")
    if not api_key:
        raise LookupError("NEWS_API_KEY is not configured")
    response = httpx.get(
        f"{NEWS_API_BASE}/everything",
        params={
            "q": query or "finance",
            "language": "en",
            "pageSize": MAX_ARTICLES,
            "sortBy": "publishedAt",
            "apiKey": api_key,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("articles", [])


def run(input: SpecialistInput) -> SpecialistAgentOutput:
    query = str(input.evidence.get("market_query") or input.task or "")
    limitations = [UNCERTAINTY_LIMITATION, NOT_ADVICE_LIMITATION]

    try:
        articles = _fetch_articles(query)
    except LookupError:
        return SpecialistAgentOutput(
            specialist="market_context",
            confidence=0.0,
            findings=[],
            recommendations=[],
            limitations=[
                "News search is not configured (NEWS_API_KEY missing); no market facts are available.",
                *limitations,
            ],
        )
    except Exception as exc:  # provider/network failure: typed unavailable, no fabrication
        return SpecialistAgentOutput(
            specialist="market_context",
            confidence=0.0,
            findings=[],
            recommendations=[],
            limitations=[
                f"News provider is unavailable ({type(exc).__name__}); no market facts are available.",
                *limitations,
            ],
        )

    findings: list[SpecialistFinding] = []
    dropped = 0
    for article in articles[:MAX_ARTICLES]:
        url = article.get("url")
        published_at = article.get("publishedAt")
        title = article.get("title")
        if not url or not published_at or not title:
            dropped += 1
            continue
        source_name = (article.get("source") or {}).get("name") or "unknown source"
        findings.append(
            SpecialistFinding(
                title=title,
                evidence=[f"{source_name}, published {published_at}"],
                risk_level="low",
                source_url=url,
                published_at=published_at,
            )
        )
    if dropped:
        limitations.append(f"{dropped} articles were dropped for missing source or timestamp.")
    if not findings:
        limitations.append("No sourced market articles matched the query.")

    return SpecialistAgentOutput(
        specialist="market_context",
        confidence=0.5 if findings else 0.2,
        findings=findings,
        recommendations=[],
        limitations=limitations,
    )
