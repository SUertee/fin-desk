"""
summaries.py
- Build frontend-friendly summary structures (by category, by month, top merchants).
"""

from collections import defaultdict
from typing import Any, Dict, List


def build_by_month_rows(by_month: dict) -> list[dict]:
    rows = []
    for month, cats in sorted(by_month.items()):
        row = {"month": month, **cats}
        rows.append(row)
    return rows


def build_category_summary(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Summarize spend by month/category and top merchants.

    Convention:
    - spend is reported as POSITIVE numbers (absolute value of negative amounts)
    - income is not counted into spend buckets
    """
    by_month_cat = defaultdict(lambda: defaultdict(float))
    by_cat_total = defaultdict(float)
    merchant_total = defaultdict(float)

    for t in transactions:
        date = t.get("date", "")
        month = date[:7] if len(date) >= 7 else "unknown"
        cat = t.get("category", "other")
        amt = t.get("amount")

        if not isinstance(amt, (int, float)):
            continue

        spend = abs(amt) if amt < 0 else 0.0
        by_month_cat[month][cat] += spend
        by_cat_total[cat] += spend

        merchant = (t.get("description") or "").strip()[:40]
        merchant_total[merchant] += spend

    by_category = sorted(
        [{"category": k, "spend": round(v, 2)} for k, v in by_cat_total.items()],
        key=lambda x: x["spend"],
        reverse=True,
    )

    top_merchants = sorted(
        [{"merchant": k, "spend": round(v, 2)} for k, v in merchant_total.items()],
        key=lambda x: x["spend"],
        reverse=True,
    )[:10]

    return {
        "by_month": {m: dict(cats) for m, cats in by_month_cat.items()},
        "by_month_rows": build_by_month_rows(
            {m: dict(cats) for m, cats in by_month_cat.items()}
        ),
        "by_category": by_category,
        "top_merchants": top_merchants,
    }
