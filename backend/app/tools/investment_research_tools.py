"""Bounded extraction and projection helpers for investment research tools."""

from __future__ import annotations

import re
from typing import Any

from app.models.investment_research import InstrumentResearchSnapshot
from app.models.market_data import MarketAssetType


_PREFIXED_SYMBOL = re.compile(r"\$([A-Za-z][A-Za-z0-9.-]{0,9})\b")
_LABELED_SYMBOL = re.compile(
    r"(?:股票|标的|代码|ticker|symbol|stock|etf)\s*[:：]?\s*([A-Za-z][A-Za-z0-9.-]{0,9})\b",
    re.IGNORECASE,
)
_UPPERCASE_SYMBOL = re.compile(r"\b([A-Z][A-Z0-9.-]{0,9})\b")
_SYMBOL_STOP_WORDS = {
    "AI",
    "API",
    "AUD",
    "CFO",
    "CNY",
    "ETF",
    "FIN",
    "IPO",
    "RMB",
    "USD",
}


def extract_instrument_reference(message: str) -> tuple[str, MarketAssetType] | None:
    """Extract only explicit ticker-like references; never infer company names."""

    text = str(message or "").strip()
    asset_type: MarketAssetType = "etf" if "etf" in text.lower() else "equity"
    candidates = [
        *(_PREFIXED_SYMBOL.findall(text)),
        *(_LABELED_SYMBOL.findall(text)),
        *(_UPPERCASE_SYMBOL.findall(text)),
    ]
    for candidate in candidates:
        normalized = candidate.upper().strip(".-")
        if normalized and normalized not in _SYMBOL_STOP_WORDS:
            return normalized, asset_type
    return None


def project_instrument_research(snapshot: InstrumentResearchSnapshot) -> dict[str, Any]:
    """Keep the agent context useful but exclude full history and provider objects."""

    bars = snapshot.history.bars
    first_close = bars[0].close.amount if bars else None
    last_close = bars[-1].close.amount if bars else None
    performance = snapshot.performance.model_dump(mode="json")
    return {
        "status": "available",
        "symbol": snapshot.symbol,
        "asset_type": snapshot.asset_type,
        "profile": {
            "name": snapshot.profile.name,
            "venue": snapshot.profile.venue,
            "currency": snapshot.profile.currency,
            "sector": snapshot.profile.sector,
            "industry": snapshot.profile.industry,
            "country": snapshot.profile.country,
            "source": snapshot.profile.source,
            "fetched_at": snapshot.profile.fetched_at.isoformat(),
        },
        "quote": snapshot.quote.model_dump(mode="json") if snapshot.quote else None,
        "history": {
            "date_from": snapshot.history.date_from.isoformat(),
            "date_to": snapshot.history.date_to.isoformat(),
            "bar_count": len(bars),
            "first_close": str(first_close) if first_close is not None else None,
            "last_close": str(last_close) if last_close is not None else None,
            "change_percent": performance.get("period_return_percent"),
            "currency": snapshot.history.currency,
            "source": snapshot.history.provider,
            "fetched_at": snapshot.history.fetched_at.isoformat(),
        },
        "performance": performance,
        "benchmark": snapshot.benchmark.model_dump(mode="json"),
        "readiness": snapshot.readiness.model_dump(mode="json"),
        "evidence": [item.model_dump(mode="json") for item in snapshot.evidence],
        "limitations": list(snapshot.limitations),
        "trade_actions_allowed": False,
    }
