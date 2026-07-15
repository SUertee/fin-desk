"""Typed contracts for native and reporting-currency AI costs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.runtime_usage import AgentRunUsage


CostStatus = Literal["complete", "partial", "not_applicable"]
CostIssue = Literal[
    "missing_pricing",
    "missing_exchange_rate",
    "historical_v1_detail_unavailable",
]


def normalize_currency(value: str) -> str:
    normalized = str(value).strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("currency must be a three-letter code")
    return normalized


class MoneyAmount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(ge=0)
    currency: str

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)


class ModelPricing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    provider: str
    model_name: str
    billing_currency: str
    input_cost_per_1m: Decimal = Field(ge=0)
    output_cost_per_1m: Decimal = Field(ge=0)
    pricing_source: str
    pricing_effective_date: date

    @field_validator("billing_currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)


class ExchangeRateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    billing_currency: str
    reporting_currency: str
    exchange_rate: Decimal = Field(gt=0)
    exchange_rate_date: date
    exchange_rate_source: str

    @field_validator("billing_currency", "reporting_currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)


class LLMStageCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    status: str
    profile: str
    provider: str | None = None
    model_name: str | None = None
    usage: AgentRunUsage = Field(default_factory=AgentRunUsage)
    pricing: ModelPricing | None = None
    billing_input_cost: MoneyAmount | None = None
    billing_output_cost: MoneyAmount | None = None
    billing_total: MoneyAmount | None = None
    reporting_total: MoneyAmount | None = None
    exchange_rate_snapshot: ExchangeRateSnapshot | None = None
    issues: list[CostIssue] = Field(default_factory=list)


class AgentRunCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CostStatus = "not_applicable"
    issues: list[CostIssue] = Field(default_factory=list)
    reporting_currency: str = "USD"
    billing_totals: list[MoneyAmount] = Field(default_factory=list)
    reporting_total: MoneyAmount | None = None
    stages: list[LLMStageCost] = Field(default_factory=list)

    @field_validator("reporting_currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)
