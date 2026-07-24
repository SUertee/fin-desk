"""Typed transaction query (nl2filters) tests."""

from datetime import date

import pytest

from app.runtime.orchestration.factory import build_finance_runtime
from app.tools import query_tools
from app.tools.query_tools import (
    QueryFilters,
    extract_query_filters,
    has_query_intent,
    run_transaction_query,
)
from tests.cfo_decision_fakes import execute

TODAY = date(2026, 7, 6)


class TestFilterExtraction:
    def test_chinese_month_and_category(self):
        filters = extract_query_filters("6月餐饮花了多少", today=TODAY)

        assert filters.date_from == "2026-06-01"
        assert filters.date_to == "2026-06-30"
        assert filters.category == "dining"
        assert filters.direction == "expense"

    def test_bare_future_month_means_most_recent(self):
        filters = extract_query_filters("12月交通花了多少", today=TODAY)

        assert filters.date_from == "2025-12-01"  # Dec 2026 hasn't happened

    def test_explicit_year(self):
        filters = extract_query_filters("2026年5月购物花了多少钱", today=TODAY)

        assert filters.date_from == "2026-05-01"
        assert filters.category == "shopping"

    def test_iso_month(self):
        filters = extract_query_filters("2026-06 housing total spent", today=TODAY)

        assert filters.date_from == "2026-06-01"
        assert filters.category == "housing"

    def test_last_month_and_income(self):
        filters = extract_query_filters("上个月收入多少", today=TODAY)

        assert filters.date_from == "2026-06-01"
        assert filters.direction == "income"

    def test_group_by_category(self):
        filters = extract_query_filters("6月各类支出多少 分类统计", today=TODAY)

        assert filters.group_by == "category"


class TestQueryIntent:
    def test_query_phrases_with_filters_trigger(self):
        assert has_query_intent("6月餐饮花了多少") is True
        assert has_query_intent("上个月总共花了多少钱") is True

    def test_generic_analysis_does_not_trigger(self):
        assert has_query_intent("帮我分析这个月消费") is False
        assert has_query_intent("hello") is False

    def test_marker_without_filters_does_not_trigger(self):
        assert has_query_intent("花了多少") is False


class TestRunQuery:
    def test_user_id_injected_and_filters_passed(self, monkeypatch):
        captured = []

        def fake_aggregate(user_id, **kwargs):
            captured.append({"user_id": user_id, **kwargs})
            if kwargs["category"] is None:
                return {"total": 19433.92, "count": 300, "groups": []}
            return {"total": 7234.82, "count": 203, "groups": []}

        monkeypatch.setattr(query_tools, "aggregate_transactions_db", fake_aggregate)
        result = run_transaction_query(
            "demo",
            QueryFilters(date_from="2026-06-01", date_to="2026-06-30", category="dining"),
        )

        assert captured[0]["user_id"] == "demo"
        assert captured[0]["category"] == "dining"
        assert captured[1]["category"] is None
        assert result["total"] == 7234.82
        assert result["filters"]["category"] == "dining"
        assert result["scope_total"] == 19433.92
        assert result["share_of_scope"] == 0.3723


@pytest.mark.asyncio
class TestEndToEnd:
    async def test_query_answer_leads_reply_and_traces(self, monkeypatch):
        def fake_aggregate(user_id, **kwargs):
            assert user_id == "demo"
            return {"total": 1234.5, "count": 42, "groups": []}

        monkeypatch.setattr(query_tools, "aggregate_transactions_db", fake_aggregate)

        runtime = build_finance_runtime(
            decision_engine=execute("finance.query_transactions")
        )
        result = await runtime.handle(
            user_id="demo",
            message="6月餐饮花了多少",
            profile={},
            transactions=[{"amount": -1, "date": "2026-06-01", "month": "2026-06"}],
            monthly_totals=[],
            chat_history=[],
            memory_context={},
        )

        assert "1,234.50" in result["reply"]
        assert "42 笔" in result["reply"]
        assert [card["label"] for card in result["data"]["summary_cards"]] == [
            "匹配金额",
            "交易笔数",
            "同期占比",
        ]
        assert result["data"]["summary_cards"][0]["value"] == "1,234.50"
        assert result["data"]["audit"]["status"] == "verified"
