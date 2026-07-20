"""Deterministic baseline portfolio construction with no learned parameters."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, getcontext

from pydantic import BaseModel, ConfigDict, Field

from research.quant_lab.contracts import NormalizedPriceRow


getcontext().prec = 28


class AllocationWeight(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    weight: Decimal = Field(ge=0, le=1)


class MomentumSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    as_of: date
    lookback_observations: int = Field(ge=2)
    score: Decimal


def equal_weight_allocations(symbols: list[str]) -> list[AllocationWeight]:
    normalized = sorted(set(symbols))
    if not normalized:
        raise ValueError("at least one symbol is required")
    if len(normalized) != len(symbols):
        raise ValueError("symbols must be unique")

    base = Decimal("1") / Decimal(len(normalized))
    allocations = [
        AllocationWeight(symbol=symbol, weight=base) for symbol in normalized[:-1]
    ]
    assigned = sum((item.weight for item in allocations), Decimal("0"))
    allocations.append(
        AllocationWeight(symbol=normalized[-1], weight=Decimal("1") - assigned)
    )
    return allocations


def momentum_signals(
    rows: list[NormalizedPriceRow],
    *,
    as_of: date,
    lookback_observations: int = 20,
) -> list[MomentumSignal]:
    if lookback_observations < 2:
        raise ValueError("lookback_observations must be at least two")

    history: dict[str, list[NormalizedPriceRow]] = defaultdict(list)
    for row in rows:
        if row.period <= as_of:
            history[row.symbol].append(row)

    signals: list[MomentumSignal] = []
    required = lookback_observations + 1
    for symbol, symbol_rows in sorted(history.items()):
        ordered = sorted(symbol_rows, key=lambda row: row.period)
        if len(ordered) < required:
            continue
        window = ordered[-required:]
        start = window[0].close
        end = window[-1].close
        signals.append(
            MomentumSignal(
                symbol=symbol,
                as_of=as_of,
                lookback_observations=lookback_observations,
                score=(end / start) - Decimal("1"),
            )
        )
    return sorted(signals, key=lambda signal: (-signal.score, signal.symbol))


def momentum_top_k_allocations(
    rows: list[NormalizedPriceRow],
    *,
    as_of: date,
    top_k: int,
    lookback_observations: int = 20,
) -> list[AllocationWeight]:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    signals = momentum_signals(
        rows,
        as_of=as_of,
        lookback_observations=lookback_observations,
    )
    selected = [signal.symbol for signal in signals[:top_k]]
    if not selected:
        raise ValueError("insufficient history for momentum baseline")
    return equal_weight_allocations(selected)
