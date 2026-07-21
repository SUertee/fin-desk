from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.investments import InvestmentAccount, PositionValuation
from app.runtime.policy.investment_policy import (
    evaluate_investment_risk,
    investment_output_violations,
)


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


def _account(status="active"):
    return InvestmentAccount(
        user_id="demo",
        account_id="broker-1",
        name="Brokerage",
        base_currency="USD",
        status=status,
        as_of=NOW,
    )


def _valuation(symbol, amount, quote_age_days=0, issues=None):
    return PositionValuation(
        account_id="broker-1",
        symbol=symbol,
        asset_type="equity",
        quantity="1",
        quote={
            "symbol": symbol,
            "asset_type": "equity",
            "price": {"amount": str(amount), "currency": "USD"},
            "quote_as_of": NOW - timedelta(days=quote_age_days),
            "source": "recorded-test-feed",
        },
        native_market_value={"amount": str(amount), "currency": "USD"},
        reporting_market_value={"amount": str(amount), "currency": "USD"},
        issues=issues or [],
    )


def test_policy_flags_disconnected_stale_and_concentrated_positions():
    result = evaluate_investment_risk(
        accounts=[_account("disconnected")],
        positions=[_valuation("AAPL", 90, 5), _valuation("BND", 10)],
        as_of=NOW,
        stale_after_days=3,
        concentration_threshold_percent=Decimal("35"),
    )

    codes = [finding.code for finding in result.findings]
    assert "disconnected_account" in codes
    assert "stale_quote" in codes
    assert "single_position_concentration" in codes
    concentrated = next(
        finding for finding in result.findings
        if finding.code == "single_position_concentration" and finding.symbols == ["AAPL"]
    )
    assert concentrated.measured_percent == Decimal("90.00")
    assert result.trade_actions_allowed is False


def test_policy_does_not_claim_concentration_for_partial_portfolio():
    missing = PositionValuation(
        account_id="broker-1",
        symbol="UNKNOWN",
        asset_type="other",
        quantity="1",
        issues=["missing_quote"],
    )
    result = evaluate_investment_risk(
        accounts=[_account()],
        positions=[_valuation("AAPL", 100), missing],
        as_of=NOW,
        stale_after_days=3,
        concentration_threshold_percent=Decimal("35"),
    )

    assert "missing_quote" in [finding.code for finding in result.findings]
    assert "single_position_concentration" not in [
        finding.code for finding in result.findings
    ]


def test_output_guard_accepts_read_only_evidence_summary():
    assert investment_output_violations(
        "AAPL returned 4.2% over the observed period. Historical prices do not predict future returns."
    ) == ()


def test_output_guard_blocks_trade_instructions_and_return_guarantees():
    assert investment_output_violations(
        "Buy AAPL now for a guaranteed return."
    ) == ("trade_instruction", "return_guarantee")
    assert investment_output_violations(
        "建议立即买入 AAPL，这是一笔稳赚的交易。"
    ) == ("trade_instruction", "return_guarantee")
