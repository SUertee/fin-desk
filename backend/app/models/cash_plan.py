"""Models for forward-looking cash, bills, debt and living budgets."""

from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


CashPlanKind = Literal["income", "housing", "debt", "budget", "purchase", "other"]


class CashPlanEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(min_length=1, max_length=120)
    kind: CashPlanKind
    amount: float = Field(gt=0)
    due_date: date
    recurrence: Literal["once", "monthly"] = "once"
    recurring_amount: float | None = Field(default=None, gt=0)
    remaining_occurrences: int | None = Field(default=None, ge=1, le=240)
    outstanding_balance: float | None = Field(default=None, ge=0)
    essential: bool = True
    status: Literal["active", "paused"] = "active"
    notes: str = Field(default="", max_length=1000)


class CashPlan(BaseModel):
    user_id: str
    currency: str = "CNY"
    cash_balance: float = Field(default=0, ge=0)
    daily_budget: float = Field(default=0, ge=0)
    monthly_budget: float = Field(default=0, ge=0)
    entries: list[CashPlanEntry] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CashPlanUpdate(BaseModel):
    currency: str = "CNY"
    cash_balance: float = Field(default=0, ge=0)
    daily_budget: float = Field(default=0, ge=0)
    monthly_budget: float = Field(default=0, ge=0)
    entries: list[CashPlanEntry] = Field(default_factory=list)
