"""Deterministic slot resolution for follow-up finance references.

Resolves "那餐饮呢?" / "那上个月呢?" style turns against TRUSTED context
(`session_memory.last_query`, `last_time_range`, `last_entities`) and
rewrites them into complete, tool-parseable questions. When a required
slot has no trusted source, it returns `needs_clarification` — it never
guesses dates, categories, transactions, or metrics.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.runtime.orchestration.intake.contracts import (
    ContextualizedTurn,
    ResolvedSlot,
    unchanged_turn,
)
from app.tools.query_tools import QueryFilters, extract_query_filters

# Canonical ledger categories -> user-facing zh labels for rewrites.
CATEGORY_ZH = {
    "dining": "餐饮",
    "transport": "交通",
    "shopping": "购物",
    "groceries": "买菜",
    "housing": "住房",
    "entertainment": "娱乐",
    "travel": "旅行",
    "utilities": "水电",
    "services": "订阅",
    "health": "医疗",
    "transfer": "转账",
    "education": "教育",
}

# "那...呢" style substitution markers; complete questions never need them.
_SUBSTITUTION_MARKERS = ("呢", "那么")
_DAY_PRONOUNS = ("这一天", "这天", "那天", "那一天")
_TXN_PRONOUNS = ("这笔", "那笔")
_EVIDENCE_REQUESTS = ("引用", "来源", "证据", "为什么这样", "依据")


def _is_evidence_request(message: str) -> bool:
    text = message or ""
    return any(marker in text for marker in _EVIDENCE_REQUESTS)


def _session_memory(memory_context: dict[str, Any] | None) -> dict[str, Any]:
    return (memory_context or {}).get("session_memory") or {}


def _last_query(memory_context: dict[str, Any] | None) -> dict[str, Any]:
    query = _session_memory(memory_context).get("last_query")
    return dict(query) if isinstance(query, dict) else {}


def _is_substitution_shape(message: str) -> bool:
    """Short reference turns only ("那餐饮呢?", "那上个月呢?").

    Long sentences that merely contain 呢 ("...有什么办法呢") are full
    questions and must never be rewritten.
    """

    text = (message or "").strip()
    compact = text.replace(" ", "")
    if len(compact) > 10:
        return False
    return any(marker in text for marker in _SUBSTITUTION_MARKERS) or text.startswith("那")


def _month_label(date_from: str, date_to: str) -> str | None:
    """Return "YYYY年M月" when the range is exactly one calendar month."""

    try:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    except (TypeError, ValueError):
        return None
    if start.day != 1 or start.replace(day=1) != end.replace(day=1):
        return None
    import calendar

    if end.day != calendar.monthrange(end.year, end.month)[1]:
        return None
    return f"{start.year}年{start.month}月"


def _metric_phrase(metric: str, direction: str) -> str:
    if metric == "expense_share":
        return "支出占比是多少"
    if direction == "income":
        return "收入多少"
    # Keep the typed-query marker ("花了多少") so the rewritten question
    # round-trips through has_query_intent/extract_query_filters.
    return "花了多少"


def _range_slot(date_from: str, date_to: str, source: str) -> ResolvedSlot:
    return ResolvedSlot(
        slot_type="date_range",
        value=f"{date_from}..{date_to}",
        source=source,
        confidence=1.0,
    )


class SlotResolver:
    """Deterministic reference resolution over trusted context only."""

    def resolve(
        self,
        raw_message: str,
        memory_context: dict[str, Any] | None = None,
        *,
        today: date | None = None,
    ) -> ContextualizedTurn:
        raw_filters = extract_query_filters(raw_message, today=today)
        last_query = _last_query(memory_context)

        # Evidence requests keep their nature: never rewritten into a fresh
        # ledger query. Slots may point at the prior topic for traceability.
        if _is_evidence_request(raw_message):
            turn = unchanged_turn(raw_message)
            focus = str(
                (_session_memory(memory_context).get("last_topic") or {}).get("focus")
                or ""
            )
            if focus:
                turn = turn.model_copy(
                    update={
                        "resolved_slots": [
                            ResolvedSlot(
                                slot_type="topic",
                                value=focus,
                                source="session_memory",
                            )
                        ]
                    }
                )
            return turn

        # Day / transaction pronouns need a concrete trusted referent.
        pronoun_turn = self._resolve_pronouns(raw_message, memory_context, last_query)
        if pronoun_turn is not None:
            return pronoun_turn

        has_raw_range = bool(raw_filters.date_from)
        has_raw_category = bool(raw_filters.category)

        # Complete query: nothing to substitute; attach raw slots only.
        if not _is_substitution_shape(raw_message) or (has_raw_range and has_raw_category):
            return self._complete_turn(raw_message, raw_filters)

        # "那餐饮呢?" — new category, reuse prior range + metric.
        if has_raw_category and not has_raw_range:
            return self._substitute_category(raw_message, raw_filters, last_query)

        # "那上个月呢?" — new range, reuse prior category + metric.
        if has_raw_range and not has_raw_category:
            return self._substitute_range(raw_message, raw_filters, last_query)

        # Substitution-shaped but carrying no recognizable slot ("那个呢?"):
        # an unresolvable reference — ask, or let the model contextualizer try.
        return self._needs_clarification(raw_message, "unresolvable_reference")

    def _complete_turn(
        self, raw_message: str, raw_filters: QueryFilters
    ) -> ContextualizedTurn:
        slots: list[ResolvedSlot] = []
        if raw_filters.date_from and raw_filters.date_to:
            slots.append(
                _range_slot(raw_filters.date_from, raw_filters.date_to, "raw_message")
            )
        if raw_filters.category:
            slots.append(
                ResolvedSlot(
                    slot_type="category",
                    value=raw_filters.category,
                    source="raw_message",
                )
            )
        if raw_filters.direction:
            slots.append(
                ResolvedSlot(
                    slot_type="direction",
                    value=raw_filters.direction,
                    source="raw_message",
                )
            )
        return unchanged_turn(raw_message).model_copy(update={"resolved_slots": slots})

    def _substitute_category(
        self,
        raw_message: str,
        raw_filters: QueryFilters,
        last_query: dict[str, Any],
    ) -> ContextualizedTurn:
        date_from = str(last_query.get("date_from") or "")
        date_to = str(last_query.get("date_to") or "")
        month = _month_label(date_from, date_to) if date_from and date_to else None
        if month is None:
            return self._needs_clarification(
                raw_message, "no_trusted_date_range_for_category_reference"
            )
        metric = str(last_query.get("metric") or "total")
        direction = str(last_query.get("direction") or "expense")
        category_zh = CATEGORY_ZH.get(raw_filters.category, raw_filters.category)
        effective = f"{month}{category_zh}{_metric_phrase(metric, direction)}？"
        return ContextualizedTurn(
            raw_message=raw_message,
            effective_message=effective,
            rewrite_applied=True,
            resolution_status="resolved",
            confidence=0.95,
            resolved_slots=[
                ResolvedSlot(
                    slot_type="category",
                    value=raw_filters.category,
                    source="raw_message",
                    raw_text=raw_message,
                ),
                _range_slot(date_from, date_to, "last_query"),
                ResolvedSlot(slot_type="metric", value=metric, source="last_query"),
                ResolvedSlot(
                    slot_type="direction", value=direction, source="last_query"
                ),
            ],
        )

    def _substitute_range(
        self,
        raw_message: str,
        raw_filters: QueryFilters,
        last_query: dict[str, Any],
    ) -> ContextualizedTurn:
        category = str(last_query.get("category") or "")
        if not category:
            return self._needs_clarification(
                raw_message, "no_trusted_category_for_time_reference"
            )
        month = _month_label(raw_filters.date_from or "", raw_filters.date_to or "")
        if month is None:
            return self._needs_clarification(
                raw_message, "unsupported_date_range_shape"
            )
        metric = str(last_query.get("metric") or "total")
        direction = str(last_query.get("direction") or "expense")
        category_zh = CATEGORY_ZH.get(category, category)
        effective = f"{month}{category_zh}{_metric_phrase(metric, direction)}？"
        return ContextualizedTurn(
            raw_message=raw_message,
            effective_message=effective,
            rewrite_applied=True,
            resolution_status="resolved",
            confidence=0.95,
            resolved_slots=[
                _range_slot(
                    raw_filters.date_from or "",
                    raw_filters.date_to or "",
                    "raw_message",
                ),
                ResolvedSlot(
                    slot_type="category", value=category, source="last_query"
                ),
                ResolvedSlot(slot_type="metric", value=metric, source="last_query"),
                ResolvedSlot(
                    slot_type="direction", value=direction, source="last_query"
                ),
            ],
        )

    def _resolve_pronouns(
        self,
        raw_message: str,
        memory_context: dict[str, Any] | None,
        last_query: dict[str, Any],
    ) -> ContextualizedTurn | None:
        text = raw_message or ""
        day_pronoun = next((p for p in _DAY_PRONOUNS if p in text), None)
        txn_pronoun = next((p for p in _TXN_PRONOUNS if p in text), None)
        if day_pronoun is None and txn_pronoun is None:
            return None

        session_memory = _session_memory(memory_context)

        if day_pronoun is not None:
            day = self._trusted_day(session_memory, last_query)
            if day is None:
                return self._needs_clarification(
                    raw_message, "no_trusted_day_for_pronoun"
                )
            effective = text.replace(day_pronoun, f"{day} ", 1)
            return ContextualizedTurn(
                raw_message=raw_message,
                effective_message=effective,
                rewrite_applied=True,
                resolution_status="resolved",
                confidence=0.9,
                resolved_slots=[
                    ResolvedSlot(
                        slot_type="date",
                        value=day,
                        source="session_memory",
                        raw_text=day_pronoun,
                    )
                ],
            )

        transaction = next(
            (
                str(entity.get("name") or "")
                for entity in session_memory.get("last_entities") or []
                if entity.get("type") == "transaction" and entity.get("name")
            ),
            None,
        )
        if transaction is None:
            return self._needs_clarification(
                raw_message, "no_trusted_transaction_for_pronoun"
            )
        return ContextualizedTurn(
            raw_message=raw_message,
            effective_message=text.replace(txn_pronoun, f"{transaction} ", 1),
            rewrite_applied=True,
            resolution_status="resolved",
            confidence=0.9,
            resolved_slots=[
                ResolvedSlot(
                    slot_type="transaction",
                    value=transaction,
                    source="session_memory",
                    raw_text=txn_pronoun,
                )
            ],
        )

    @staticmethod
    def _trusted_day(
        session_memory: dict[str, Any], last_query: dict[str, Any]
    ) -> str | None:
        date_from = str(last_query.get("date_from") or "")
        date_to = str(last_query.get("date_to") or "")
        if date_from and date_from == date_to:
            return date_from
        time_range = session_memory.get("last_time_range") or {}
        start = str(time_range.get("start") or "")
        end = str(time_range.get("end") or "")
        if start and start == end and len(start) == 10:
            return start
        for entity in session_memory.get("last_entities") or []:
            if entity.get("type") == "date" and entity.get("name"):
                return str(entity["name"])
        return None

    @staticmethod
    def _needs_clarification(raw_message: str, reason: str) -> ContextualizedTurn:
        return ContextualizedTurn(
            raw_message=raw_message,
            effective_message=raw_message,
            rewrite_applied=False,
            resolution_status="needs_clarification",
            confidence=0.0,
            ambiguity_reason=reason,
        )
