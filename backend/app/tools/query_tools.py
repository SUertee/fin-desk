"""Typed transaction query (nl2filters).

Natural language maps to typed filter parameters — never to SQL. The
deterministic runtime extracts filters with the keyword rules below; a future
LLM-backed CFO fills the same `QueryFilters` contract, so the tool surface
does not change when the extraction gets smarter.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel

from app.connectors.postgres.transactions_store import aggregate_transactions_db


class QueryFilters(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    category: Optional[str] = None
    merchant_contains: Optional[str] = None
    direction: Optional[str] = None  # expense | income
    group_by: Optional[str] = None  # category | month | counterparty | day

    def has_any(self) -> bool:
        return any(
            getattr(self, field) is not None
            for field in ("date_from", "date_to", "category", "merchant_contains")
        )


# zh/en aliases → canonical ledger categories
CATEGORY_ALIASES = {
    "餐饮": "dining", "吃饭": "dining", "外卖": "dining", "dining": "dining",
    "food": "dining", "咖啡": "dining",
    "交通": "transport", "出行": "transport", "打车": "transport",
    "地铁": "transport", "transport": "transport",
    "购物": "shopping", "网购": "shopping", "shopping": "shopping",
    "买菜": "groceries", "超市": "groceries", "生鲜": "groceries",
    "groceries": "groceries",
    "房租": "housing", "住房": "housing", "housing": "housing", "rent": "housing",
    "娱乐": "entertainment", "entertainment": "entertainment",
    "旅行": "travel", "旅游": "travel", "酒店": "travel", "travel": "travel",
    "水电": "utilities", "话费": "utilities", "utilities": "utilities",
    "订阅": "services", "会员": "services", "services": "services",
    "医疗": "health", "看病": "health", "health": "health",
    "转账": "transfer", "红包": "transfer", "transfer": "transfer",
    "教育": "education", "education": "education",
}

_QUERY_MARKERS = (
    "花了多少", "花了", "多少钱", "支出多少", "收入多少", "总共", "合计",
    "占比", "比例", "how much", "total spent", "spend on", "spent on",
    "percentage", "share of",
)

_MONTH_CN = re.compile(r"(?:(\d{4})\s*年)?\s*(\d{1,2})\s*月")
_MONTH_ISO = re.compile(r"(\d{4})-(\d{2})(?!-\d)")


def _month_range(year: int, month: int) -> tuple[str, str]:
    import calendar

    last = calendar.monthrange(year, month)[1]
    return (
        date(year, month, 1).isoformat(),
        date(year, month, last).isoformat(),
    )


def extract_query_filters(
    message: str, *, today: date | None = None
) -> QueryFilters:
    """Deterministic filter extraction for common query phrasings."""

    text = (message or "").lower()
    now = today or date.today()
    filters = QueryFilters()

    iso = _MONTH_ISO.search(text)
    cn = _MONTH_CN.search(message or "")
    if iso:
        filters.date_from, filters.date_to = _month_range(int(iso.group(1)), int(iso.group(2)))
    elif cn:
        year = int(cn.group(1)) if cn.group(1) else now.year
        month = int(cn.group(2))
        if 1 <= month <= 12:
            # A bare month like 6月 means the most recent such month
            if not cn.group(1) and (year, month) > (now.year, now.month):
                year -= 1
            filters.date_from, filters.date_to = _month_range(year, month)
    elif "上个月" in (message or "") or "last month" in text:
        year, month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
        filters.date_from, filters.date_to = _month_range(year, month)
    elif "这个月" in (message or "") or "本月" in (message or "") or "this month" in text:
        filters.date_from, filters.date_to = _month_range(now.year, now.month)

    for alias, canonical in CATEGORY_ALIASES.items():
        if alias in text:
            filters.category = canonical
            break

    if "收入" in (message or "") or "income" in text or "earn" in text:
        filters.direction = "income"
    else:
        filters.direction = "expense"

    if any(k in text for k in ("按分类", "各类", "分类统计", "by category", "breakdown")):
        filters.group_by = "category"
    elif any(k in text for k in ("按月", "每月", "by month", "monthly")):
        filters.group_by = "month"

    return filters


def has_query_intent(message: str) -> bool:
    """True when the message asks for a figure the typed query can answer."""

    text = (message or "").lower()
    if not any(marker in text for marker in _QUERY_MARKERS):
        return False
    filters = extract_query_filters(message)
    return filters.has_any()


def run_transaction_query(
    user_id: str, filters: QueryFilters
) -> dict[str, Any]:
    """Execute the typed query. `user_id` is runtime-injected, never agent-supplied."""

    result = aggregate_transactions_db(
        user_id,
        date_from=filters.date_from,
        date_to=filters.date_to,
        category=filters.category,
        merchant_contains=filters.merchant_contains,
        direction=filters.direction,
        group_by=filters.group_by,
    )
    payload = {
        "filters": filters.model_dump(exclude_none=True),
        "total": result["total"],
        "count": result["count"],
        "groups": result["groups"],
    }
    if filters.category:
        scope = aggregate_transactions_db(
            user_id,
            date_from=filters.date_from,
            date_to=filters.date_to,
            category=None,
            merchant_contains=filters.merchant_contains,
            direction=filters.direction,
            group_by=None,
        )
        scope_total = float(scope["total"])
        payload["scope_total"] = scope_total
        payload["share_of_scope"] = (
            round(float(result["total"]) / scope_total, 4)
            if scope_total > 0
            else None
        )
    return payload
