"""Deterministic specialist registry used by the FinDesk runtime."""

from __future__ import annotations

from typing import Callable

from app.agents.specialists import (
    auditor,
    budget_coach,
    expense_analyst,
    investment_research,
    market_context,
)
from app.agents.specialists.contracts import SpecialistAgentOutput, SpecialistInput

SpecialistRun = Callable[[SpecialistInput], SpecialistAgentOutput]

REGISTRY: dict[str, SpecialistRun] = {
    "expense_analyst": expense_analyst.run,
    "budget_coach": budget_coach.run,
    "auditor": auditor.run,
    "market_context": market_context.run,
    "investment_research": investment_research.run,
}
