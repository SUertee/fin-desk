"""Deterministic personal-finance prerequisites for investment research."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.models.costing import MoneyAmount
from app.models.investment_research import (
    InvestmentReadinessAssessment,
    InvestmentReadinessFinding,
)
from app.models.user import UserProfile


MONTH_QUANTUM = Decimal("0.01")
MINIMUM_RESERVE_MONTHS = Decimal("3")


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def evaluate_investment_readiness(
    profile: UserProfile,
) -> InvestmentReadinessAssessment:
    """Assess financial foundation without recommending an allocation or trade."""

    currency = profile.cost_preferences.reporting_currency
    income = _decimal(profile.monthly_income)
    expenses = _decimal(profile.monthly_expenses)
    liquid_amount = _decimal(profile.assets.cash_balance) + _decimal(
        profile.assets.savings
    )
    liabilities_amount = _decimal(profile.assets.liabilities)
    findings: list[InvestmentReadinessFinding] = []
    limitations = [
        "Readiness describes personal-finance prerequisites, not investment suitability or expected returns."
    ]

    if income <= 0:
        findings.append(
            InvestmentReadinessFinding(
                code="missing_monthly_income",
                severity="high",
                title="Monthly income is not configured",
                detail="Add a stable monthly income baseline before using investment-readiness conclusions.",
            )
        )
    if expenses <= 0:
        findings.append(
            InvestmentReadinessFinding(
                code="missing_monthly_expenses",
                severity="high",
                title="Monthly expenses are not configured",
                detail="Add recurring monthly expenses before calculating cash flow or reserve coverage.",
            )
        )

    monthly_cash_flow = income - expenses if income > 0 and expenses > 0 else None
    reserve_months = (
        (liquid_amount / expenses).quantize(MONTH_QUANTUM, rounding=ROUND_HALF_UP)
        if expenses > 0 and liquid_amount >= 0
        else None
    )
    if monthly_cash_flow is not None and monthly_cash_flow < 0:
        findings.append(
            InvestmentReadinessFinding(
                code="negative_monthly_cash_flow",
                severity="high",
                title="Monthly cash flow is negative",
                detail="Current recurring expenses exceed configured monthly income.",
            )
        )
    if reserve_months is not None and reserve_months < MINIMUM_RESERVE_MONTHS:
        findings.append(
            InvestmentReadinessFinding(
                code="low_liquid_reserve",
                severity="medium",
                title="Liquid reserve is below three months",
                detail=f"Configured cash and savings cover {reserve_months} months of recurring expenses.",
            )
        )
    if liabilities_amount > 0:
        findings.append(
            InvestmentReadinessFinding(
                code="liabilities_present",
                severity="info",
                title="Liabilities require separate review",
                detail="Liabilities are recorded, but interest rates and repayment terms are not available in this assessment.",
            )
        )
        limitations.append(
            "Recorded liabilities are disclosed without assuming they are high-interest debt."
        )

    required_inputs_missing = income <= 0 or expenses <= 0
    caution = any(item.severity in {"medium", "high"} for item in findings)
    status = (
        "insufficient_data"
        if required_inputs_missing
        else "caution" if caution else "ready"
    )
    return InvestmentReadinessAssessment(
        status=status,
        reporting_currency=currency,
        monthly_cash_flow=monthly_cash_flow,
        liquid_reserve=MoneyAmount(amount=max(liquid_amount, Decimal("0")), currency=currency),
        reserve_months=reserve_months,
        liabilities=MoneyAmount(
            amount=max(liabilities_amount, Decimal("0")),
            currency=currency,
        ),
        risk_tolerance=profile.risk_tolerance,
        findings=findings,
        limitations=limitations,
    )
