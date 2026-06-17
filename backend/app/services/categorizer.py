"""
categorizer.py
- Deterministic transaction categorization using regex rules.
- We return both category and confidence for explainability.
"""

import re
from typing import Tuple

# Regex rules: (pattern, category)
CATEGORY_RULES = [
    (r"(coles|woolworths|aldi|iga|market|grocery)", "groceries"),
    (r"(uber|ola|didi|taxi|opal|train|bus|metro)", "transport"),
    (
        r"(mr coconut|monster curry|cafe|restaurant|joe'?s|food|eat|bar|bistro)",
        "dining",
    ),
    (
        r"(billi|electric|gas|water|utility|internet|telstra|optus|vodafone)",
        "utilities",
    ),
    (r"(rent|landlord|strata|mortgage)", "housing"),
    (r"(interest|fee|international transaction fee|charge)", "fees_interest"),
    (r"(transfer|fast transfer|payid)", "transfer"),
]


def rule_categorize(description: str) -> Tuple[str, float]:
    """
    Categorize a transaction description via regex rules.

    Returns:
        (category, confidence)
    """
    text = (description or "").lower()
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, text):
            return category, 0.85
    return "other", 0.30


def enrich_transactions(transactions: list[dict]) -> list[dict]:
    """
    Add category + confidence to each transaction.
    This keeps the LLM stage cleaner and more reliable.
    """
    enriched = []
    for t in transactions:
        desc = t.get("description", "")
        cat, conf = rule_categorize(desc)
        enriched.append({**t, "category": cat, "cat_confidence": conf})
    return enriched
