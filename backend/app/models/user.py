"""
User-related Pydantic models: profile, assets, preferences, profile update.
"""

from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.costing import normalize_currency


class AssetSnapshot(BaseModel):
    cash_balance: float = Field(0.0, description="Cash/checking balance")
    savings: float = Field(0.0, description="Savings deposits")
    investments: float = Field(0.0, description="Investment assets")
    liabilities: float = Field(0.0, description="Liabilities")

    @property
    def net_worth(self) -> float:
        return self.cash_balance + self.savings + self.investments - self.liabilities


class UserPreferences(BaseModel):
    """CFO personalization settings consumed by the response composer."""

    response_tone: Literal["concise", "balanced", "comprehensive"] = "balanced"
    preferred_language: Literal["en", "zh", "auto"] = "auto"
    evidence_level: Literal["brief", "detailed", "audit_heavy"] = "detailed"


class CostReportingPreferences(BaseModel):
    """Finance-facing currency and AI budget preferences."""

    model_config = ConfigDict(extra="forbid")

    reporting_currency: str = "USD"
    monthly_ai_budget: Decimal | None = Field(default=None, ge=0)

    @field_validator("reporting_currency")
    @classmethod
    def validate_reporting_currency(cls, value: str) -> str:
        return normalize_currency(value)


class UserProfile(BaseModel):
    user_id: str = "demo"
    name: str = ""
    occupation: str = ""
    financial_goals: List[str] = Field(default_factory=list)
    risk_tolerance: str = "moderate"
    assets: AssetSnapshot = Field(default_factory=AssetSnapshot)
    monthly_income: float = 0.0
    monthly_expenses: float = 0.0
    notes: str = Field("", description="Additional financial notes")
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    cost_preferences: CostReportingPreferences = Field(
        default_factory=CostReportingPreferences
    )


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    occupation: Optional[str] = None
    financial_goals: Optional[List[str]] = None
    risk_tolerance: Optional[str] = None
    cash_balance: Optional[float] = None
    savings: Optional[float] = None
    investments: Optional[float] = None
    liabilities: Optional[float] = None
    monthly_income: Optional[float] = None
    monthly_expenses: Optional[float] = None
    notes: Optional[str] = None
    preferences: Optional[UserPreferences] = None
    cost_preferences: Optional[CostReportingPreferences] = None
