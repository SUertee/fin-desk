"""Deterministic helpers for checking claims against structured evidence."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


NUMBER_RE = re.compile(r"(?<![\w])[-+]?\d[\d,]*(?:\.\d+)?%?")
ISO_DATE_RE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
_RATIO_FIELD_MARKERS = ("ratio", "share", "rate", "percent", "confidence")


def normalize_number(token: str) -> Decimal | None:
    try:
        return Decimal(token.replace(",", "").rstrip("%")).normalize()
    except InvalidOperation:
        return None


def extract_number_tokens(text: str, *, exclude_iso_dates: bool = False) -> list[str]:
    candidate = ISO_DATE_RE.sub(" ", text) if exclude_iso_dates else text
    return NUMBER_RE.findall(candidate)


def collect_numbers(value: Any) -> set[Decimal]:
    numbers: set[Decimal] = set()
    if isinstance(value, dict):
        for item in value.values():
            numbers.update(collect_numbers(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            numbers.update(collect_numbers(item))
    elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        numbers.add(Decimal(str(value)).normalize())
    elif isinstance(value, str):
        for token in extract_number_tokens(value):
            normalized = normalize_number(token)
            if normalized is not None:
                numbers.add(normalized)
    return numbers


def collect_supported_numbers(value: Any, *, field_name: str = "") -> set[Decimal]:
    """Collect exact values plus percentage projections from ratio-like fields."""

    numbers: set[Decimal] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            numbers.update(collect_supported_numbers(item, field_name=str(key)))
        return numbers
    if isinstance(value, (list, tuple)):
        for item in value:
            numbers.update(collect_supported_numbers(item, field_name=field_name))
        return numbers

    direct = collect_numbers(value)
    numbers.update(direct)
    normalized_field = field_name.lower()
    if any(marker in normalized_field for marker in _RATIO_FIELD_MARKERS):
        numbers.update(number * 100 for number in direct if abs(number) <= 1)
    return numbers


def collect_iso_dates(value: Any) -> set[str]:
    dates: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            dates.update(collect_iso_dates(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            dates.update(collect_iso_dates(item))
    elif isinstance(value, str):
        dates.update(ISO_DATE_RE.findall(value))
    return dates
