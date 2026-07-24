"""Workspace linkage tests: brief endpoint, preferences, request_id, hints."""

import pytest

from app.models.user import UserPreferences, UserProfile
from app.routes import workspace as workspace_route
from app.routes.health import health
from app.runtime.orchestration.factory import build_finance_runtime
from tests.cfo_decision_fakes import execute

TRANSACTIONS = [
    {
        "date": "2026-06-10",
        "month": "2026-06",
        "description": "房租",
        "counterparty": "房东",
        "amount": -7000.0,
        "category": "housing",
        "is_duplicate": False,
    },
    {
        "date": "2026-06-16",
        "month": "2026-06",
        "description": "火车票",
        "counterparty": "12306",
        "amount": -694.0,
        "category": "transport",
        "is_duplicate": False,
    },
]

MONTHLY_TOTALS = [{"month": "2026-06", "income": 12628.8, "expense": 19433.92, "net": -6805.12}]


def _profile(**preferences) -> dict:
    return UserProfile(
        user_id="demo",
        monthly_income=10000,
        preferences=UserPreferences(**preferences),
    ).model_dump()


async def _run(message: str, *, preferences: dict | None = None, **kwargs) -> dict:
    runtime = build_finance_runtime(decision_engine=execute("finance.expense_review"))
    return await runtime.handle(
        user_id="demo",
        message=message,
        profile=_profile(**(preferences or {})),
        transactions=TRANSACTIONS,
        monthly_totals=MONTHLY_TOTALS,
        chat_history=[],
        memory_context={},
        **kwargs,
    )


@pytest.mark.asyncio
class TestRequestId:
    async def test_chat_payload_carries_request_id(self):
        result = await _run("分析我的消费")

        assert result["request_id"]
        assert len(result["request_id"]) >= 32  # uuid-format trace request id


@pytest.mark.asyncio
class TestPreferences:
    async def test_preferred_language_zh_changes_reply(self):
        zh = await _run("analyze my spending", preferences={"preferred_language": "zh"})
        en = await _run("analyze my spending", preferences={"preferred_language": "en"})

        assert "净现金流" in zh["reply"]
        assert "net cash flow" in en["reply"].lower()

    async def test_auto_language_follows_message(self):
        zh = await _run("帮我分析这个月消费")
        assert "净现金流" in zh["reply"]

    async def test_tone_changes_reply_length(self):
        concise = await _run("分析消费", preferences={"response_tone": "concise", "preferred_language": "en"})
        comprehensive = await _run(
            "分析消费", preferences={"response_tone": "comprehensive", "preferred_language": "en"}
        )

        assert len(concise["reply"]) < len(comprehensive["reply"])
        assert "In total:" in comprehensive["reply"]

    async def test_evidence_brief_truncates_findings(self):
        brief = await _run("分析消费支出", preferences={"evidence_level": "brief"})
        for finding in brief["data"]["findings"]:
            assert len(finding["evidence"]) <= 1

    async def test_audit_heavy_reports_confidence(self):
        heavy = await _run(
            "分析消费", preferences={"evidence_level": "audit_heavy", "preferred_language": "en"}
        )
        assert "Audit confidence" in heavy["reply"]

@pytest.mark.asyncio
class TestWorkspaceBrief:
    async def test_brief_from_orchestration_path(self, monkeypatch):
        monkeypatch.setattr(
            workspace_route._runtime,
            "decision_engine",
            execute("finance.expense_review"),
        )
        monkeypatch.setattr(
            workspace_route, "list_transactions_db", lambda u, limit=2000: TRANSACTIONS
        )
        monkeypatch.setattr(
            workspace_route,
            "get_latest_analysis_run_db",
            lambda u: {"monthly_totals": MONTHLY_TOTALS},
        )
        monkeypatch.setattr(
            workspace_route, "get_profile", lambda u: UserProfile(user_id=u)
        )

        brief = await workspace_route.get_workspace_brief("demo")

        assert brief.has_data is True
        assert brief.headline  # CFO judgment sentence present
        assert brief.request_id
        assert brief.period.date_from == "2026-06-10"
        assert brief.period.date_to == "2026-06-16"
        assert len(brief.summary_cards) == 3
        assert brief.audit is not None

    async def test_brief_empty_state(self, monkeypatch):
        monkeypatch.setattr(
            workspace_route, "list_transactions_db", lambda u, limit=2000: []
        )

        brief = await workspace_route.get_workspace_brief("demo")

        assert brief.has_data is False
        assert brief.summary_cards == []
        assert brief.period is None


class TestHealthTruth:
    def test_health_reports_actual_chat_runtime(self):
        payload = health()

        assert payload["agent_runtime"] == "self_hosted_cfo_agent"
        assert "analysis_runtime" not in payload
        assert payload["runtime_components"].count("orchestration.finance_runtime") == 1
        assert "get_investment_research_context" in payload["controlled_tools"]
        assert "consult_investment_research" in payload["specialist_agent_tools"]
        assert payload["capabilities"] == {
            "investment_research": "read_only",
            "hypothetical_scenarios": True,
            "trade_execution": False,
        }
