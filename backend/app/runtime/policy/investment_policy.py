"""Deterministic, non-trading portfolio risk policy."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.models.investments import (
    InvestmentAccount,
    InvestmentRiskAssessment,
    InvestmentRiskFinding,
    PositionValuation,
)


PERCENT_QUANTUM = Decimal("0.01")


def evaluate_investment_risk(
    *,
    accounts: list[InvestmentAccount],
    positions: list[PositionValuation],
    as_of: datetime,
    stale_after_days: int,
    concentration_threshold_percent: Decimal,
) -> InvestmentRiskAssessment:
    findings: list[InvestmentRiskFinding] = []

    disconnected = sorted(
        account.account_id for account in accounts if account.status == "disconnected"
    )
    if disconnected:
        findings.append(
            InvestmentRiskFinding(
                code="disconnected_account",
                severity="medium",
                title="Investment account data is disconnected",
                detail="One or more accounts may not reflect current holdings.",
                account_ids=disconnected,
            )
        )

    for position in positions:
        if "missing_quote" in position.issues:
            findings.append(
                InvestmentRiskFinding(
                    code="missing_quote",
                    severity="high",
                    title=f"No sourced quote for {position.symbol}",
                    detail="This position is excluded from the complete portfolio total.",
                    symbols=[position.symbol],
                    account_ids=[position.account_id],
                )
            )
        if "missing_exchange_rate" in position.issues:
            findings.append(
                InvestmentRiskFinding(
                    code="missing_exchange_rate",
                    severity="high",
                    title=f"No exchange-rate snapshot for {position.symbol}",
                    detail="Native value is preserved but reporting-currency value is unavailable.",
                    symbols=[position.symbol],
                    account_ids=[position.account_id],
                )
            )
        if position.quote and as_of - position.quote.quote_as_of > timedelta(
            days=stale_after_days
        ):
            findings.append(
                InvestmentRiskFinding(
                    code="stale_quote",
                    severity="medium",
                    title=f"Quote for {position.symbol} is stale",
                    detail=(
                        f"Quote is older than the configured {stale_after_days}-day "
                        "freshness boundary."
                    ),
                    symbols=[position.symbol],
                    account_ids=[position.account_id],
                )
            )

    complete_values = [
        position.reporting_market_value.amount
        for position in positions
        if position.reporting_market_value is not None
    ]
    if positions and len(complete_values) == len(positions):
        total = sum(complete_values, Decimal("0"))
        if total > 0:
            for position in positions:
                value = position.reporting_market_value
                if value is None:
                    continue
                percent = (value.amount / total * Decimal("100")).quantize(
                    PERCENT_QUANTUM, rounding=ROUND_HALF_UP
                )
                if percent > concentration_threshold_percent:
                    findings.append(
                        InvestmentRiskFinding(
                            code="single_position_concentration",
                            severity="high",
                            title=f"{position.symbol} is a concentrated position",
                            detail="Measured exposure exceeds the configured portfolio threshold.",
                            symbols=[position.symbol],
                            account_ids=[position.account_id],
                            measured_percent=percent,
                            threshold_percent=concentration_threshold_percent,
                        )
                    )

    return InvestmentRiskAssessment(findings=findings)
