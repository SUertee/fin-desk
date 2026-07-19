import pytest

from app.connectors.market_data.errors import MarketDataBudgetExceeded
from app.runtime.policy.market_outbound_policy import OutboundCallBudget


def test_outbound_budget_counts_provider_calls():
    budget = OutboundCallBudget(2)
    budget.consume()
    assert budget.snapshot().model_dump() == {"budget": 2, "used": 1, "remaining": 1}


def test_outbound_budget_refuses_call_before_external_io():
    budget = OutboundCallBudget(1)
    budget.consume()
    with pytest.raises(MarketDataBudgetExceeded, match="exhausted"):
        budget.consume()
