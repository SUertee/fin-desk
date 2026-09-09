"""Transactions route tests: daily totals and date-range filtering."""

import pytest

from app.routes import transactions as transactions_route


@pytest.fixture
def store(monkeypatch):
    state = {"daily": [], "transactions": [], "inserted": [], "calls": []}

    def fake_daily(user_id, date_from, date_to):
        state["calls"].append(("daily", user_id, date_from, date_to))
        return list(state["daily"])

    def fake_list(user_id, limit, date_from=None, date_to=None):
        state["calls"].append(("list", user_id, limit, date_from, date_to))
        return list(state["transactions"])

    monkeypatch.setattr(transactions_route, "list_daily_totals_db", fake_daily)
    monkeypatch.setattr(transactions_route, "list_transactions_db", fake_list)
    monkeypatch.setattr(
        transactions_route,
        "insert_transactions_db",
        lambda user_id, items: state["inserted"].append((user_id, items)) or True,
    )
    return state


class TestDailyTotals:
    def test_returns_days_and_month_totals(self, store):
        store["daily"] = [
            {"date": "2026-06-10", "expense": 7000.0, "income": 0.0, "count": 2},
            {"date": "2026-06-16", "expense": 1290.0, "income": 219.0, "count": 5},
        ]

        result = transactions_route.get_daily_totals("demo", month="2026-06")

        assert result["month"] == "2026-06"
        assert len(result["days"]) == 2
        assert result["totals"] == {"expense": 8290.0, "income": 219.0, "count": 7}

    def test_month_window_covers_full_month(self, store):
        transactions_route.get_daily_totals("demo", month="2026-02")

        assert store["calls"][0] == ("daily", "demo", "2026-02-01", "2026-02-28")

    def test_malformed_month_rejected(self, store):
        response = transactions_route.get_daily_totals("demo", month="2026-13")

        assert response.status_code == 400
        assert not store["calls"]

    def test_empty_month(self, store):
        result = transactions_route.get_daily_totals("demo", month="2026-07")

        assert result["days"] == []
        assert result["totals"] == {"expense": 0, "income": 0, "count": 0}


class TestDateRangeFilter:
    def test_single_day_drilldown_passes_range(self, store):
        transactions_route.get_transactions(
            "demo", date_from="2026-06-10", date_to="2026-06-10"
        )

        assert store["calls"][0] == ("list", "demo", 500, "2026-06-10", "2026-06-10")

    def test_no_range_by_default(self, store):
        transactions_route.get_transactions("demo")

        assert store["calls"][0] == ("list", "demo", 500, None, None)


class TestManualTransaction:
    def test_creates_expense_waiting_for_statement_reconciliation(self, store):
        payload = transactions_route.ManualTransactionRequest(
            amount=18.5,
            occurred_at="2026-09-09T08:20:00+08:00",
            counterparty="早餐店",
            description="早餐",
            category="dining",
            payment_method="alipay",
            meal_tag="breakfast",
        )

        result = transactions_route.create_manual_transaction("demo", payload)

        user_id, items = store["inserted"][0]
        item = items[0]
        assert user_id == "demo"
        assert item["date"] == "2026-09-09"
        assert item["amount"] == -18.5
        assert item["type"] == "manual_expense"
        assert item["source"] == "manual"
        assert item["status"] == "awaiting_statement"
        assert item["raw"]["manual"]["meal_tag"] == "breakfast"
        assert result["item"]["external_id"].startswith("manual:")

    def test_rejects_zero_amount(self):
        with pytest.raises(ValueError):
            transactions_route.ManualTransactionRequest(amount=0)

    def test_refund_is_positive_and_keeps_entry_type(self, store):
        payload = transactions_route.ManualTransactionRequest(
            amount=28,
            entry_type="refund",
            category="refund",
        )

        transactions_route.create_manual_transaction("demo", payload)

        item = store["inserted"][0][1][0]
        assert item["amount"] == 28
        assert item["type"] == "manual_refund"
        assert item["raw"]["manual"]["entry_type"] == "refund"

    def test_transfer_has_zero_cashflow_but_preserves_amount_and_accounts(self, store):
        payload = transactions_route.ManualTransactionRequest(
            amount=500,
            entry_type="transfer",
            payment_method="银行卡",
            destination_account="支付宝",
        )

        transactions_route.create_manual_transaction("demo", payload)

        item = store["inserted"][0][1][0]
        assert item["amount"] == 0
        assert item["gross_amount"] == 500
        assert item["category"] == "transfer"
        assert item["raw"]["manual"]["destination_account"] == "支付宝"
