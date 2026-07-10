"""Workspace linkage tests: brief endpoint, preferences, request_id, hints."""

import pytest

from app.models.user import UserPreferences, UserProfile
from app.routes import workspace as workspace_route
from app.routes.health import health
from app.runtime.orchestration.finance_runtime import FinanceRuntime
from app.runtime.policy.runtime_policy import evaluate_runtime_policy

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
    runtime = FinanceRuntime()
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


class TestSpecialistHint:
    def test_hint_adds_specialist(self):
        policy = evaluate_runtime_policy(
            "what is my balance", transactions=[{"amount": 1}],
            requested_specialist="budget_coach",
        )
        assert "budget_coach" in policy.required_specialists

    def test_hint_never_removes_policy_selection(self):
        policy = evaluate_runtime_policy(
            "帮我分析消费", transactions=[{"amount": 1}],
            requested_specialist="budget_coach",
        )
        assert "expense_analyst" in policy.required_specialists
        assert "budget_coach" in policy.required_specialists

    def test_auditor_and_unknown_names_are_not_hintable(self):
        for name in ("auditor", "market_context", "hacker"):
            policy = evaluate_runtime_policy(
                "hello", transactions=[{"amount": 1}], requested_specialist=name
            )
            assert name not in policy.required_specialists


@pytest.mark.asyncio
class TestWorkspaceBrief:
    async def test_brief_from_orchestration_path(self, monkeypatch):
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

        assert payload["agent_runtime"] == "self_hosted_deterministic"
        assert payload["analysis_runtime"] == "openai_agents_sdk"
