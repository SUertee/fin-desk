"""Deterministic, non-trading portfolio risk policy."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.models.investments import (
    InvestmentAccount,
    InvestmentRiskAssessment,
    InvestmentRiskFinding,
    PositionValuation,
)


PERCENT_QUANTUM = Decimal("0.01")

_TRADE_INSTRUCTION_PATTERNS = (
    re.compile(
        r"\b(?:buy|sell|short)\s+(?:shares?\s+(?:of\s+)?|the\s+)?[A-Z][A-Z0-9.-]{0,9}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:you should|i recommend|recommend|consider)\s+(?:buying|selling|shorting)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?:买入|卖出|下单|建仓|加仓|减仓|清仓|做多|做空)"),
)
_RETURN_GUARANTEE_PATTERNS = (
    re.compile(r"\bguaranteed?\s+(?:profit|return)\b", re.IGNORECASE),
    re.compile(r"\brisk[- ]?free\s+(?:profit|return)\b", re.IGNORECASE),
    re.compile(r"(?:保证收益|保证回报|保本保收益|稳赚|无风险收益)"),
)


def investment_output_violations(text: str) -> tuple[str, ...]:
    """Return bounded policy codes for unsafe investment-facing text."""

    content = str(text or "")
    violations: list[str] = []
    if any(pattern.search(content) for pattern in _TRADE_INSTRUCTION_PATTERNS):
        violations.append("trade_instruction")
    if any(pattern.search(content) for pattern in _RETURN_GUARANTEE_PATTERNS):
        violations.append("return_guarantee")
    return tuple(violations)


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
        if position.quote and position.quote.timestamp_basis == "retrieval_time":
            findings.append(
                InvestmentRiskFinding(
                    code="retrieval_timed_quote",
                    severity="info",
                    title=f"{position.symbol} quote uses retrieval time",
                    detail=(
                        "The upstream source did not provide an exchange timestamp; "
                        "the displayed time records when FinDesk retrieved the quote."
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
