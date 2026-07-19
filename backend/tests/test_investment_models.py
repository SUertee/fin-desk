from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.investments import InvestmentAccount, MarketQuote


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


def test_investment_contracts_normalize_symbols_and_currencies():
    quote = MarketQuote(
        symbol=" aapl ",
        asset_type="equity",
        price={"amount": "210.25", "currency": "usd"},
        quote_as_of=NOW,
        source="recorded-test-feed",
    )

    assert quote.symbol == "AAPL"
    assert quote.price.currency == "USD"


def test_market_quote_rejects_unsourced_or_non_positive_price():
    with pytest.raises(ValidationError):
        MarketQuote(
            symbol="AAPL",
            asset_type="equity",
            price={"amount": "0", "currency": "USD"},
            quote_as_of=NOW,
            source="",
        )


def test_investment_timestamps_must_be_timezone_aware():
    with pytest.raises(ValidationError, match="timezone-aware"):
        InvestmentAccount(
            user_id="demo",
            account_id="broker-1",
            name="Brokerage",
            base_currency="USD",
            as_of=datetime(2026, 7, 19, 10, 0),
        )


def test_investment_contracts_reject_execution_fields():
    with pytest.raises(ValidationError):
        InvestmentAccount(
            user_id="demo",
            account_id="broker-1",
            name="Brokerage",
            base_currency="USD",
            as_of=NOW,
            place_order=True,
        )
