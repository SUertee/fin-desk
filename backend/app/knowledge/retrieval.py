"""Deterministic lexical query helpers shared by retrieval adapters."""

from __future__ import annotations

import re

from app.tools.query_tools import has_query_intent

_ENGLISH_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]+", re.IGNORECASE)
_CJK_SEQUENCE = re.compile(r"[\u3400-\u9fff]+")
_STOPWORDS = {
    "about",
    "and",
    "are",
    "can",
    "for",
    "how",
    "should",
    "the",
    "what",
    "when",
    "with",
    "多少",
    "什么",
    "应该",
    "怎么",
}


def lexical_terms(text: str, *, limit: int = 12) -> tuple[list[str], list[str]]:
    """Return bounded English tokens and CJK bigrams for parameterized SQL."""

    normalized = " ".join(text.lower().split())
    english = [
        token
        for token in _ENGLISH_TOKEN.findall(normalized)
        if token not in _STOPWORDS and len(token) >= 2
    ]
    cjk: list[str] = []
    for sequence in _CJK_SEQUENCE.findall(normalized):
        if len(sequence) == 2 and sequence not in _STOPWORDS:
            cjk.append(sequence)
            continue
        cjk.extend(
            sequence[index : index + 2]
            for index in range(max(0, len(sequence) - 1))
            if sequence[index : index + 2] not in _STOPWORDS
        )
    return (
        list(dict.fromkeys(english))[:limit],
        list(dict.fromkeys(cjk))[:limit],
    )


def should_retrieve_knowledge(
    message: str,
    *,
    has_market_context: bool,
    has_investment_research: bool,
) -> bool:
    """Select reviewed guidance only after routing has chosen finance analysis."""

    if has_query_intent(message):
        return False
    return not has_market_context and not has_investment_research
