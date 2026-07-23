"""LLM-composed CFO reply tests (fake DeepSeek client, fully offline)."""

import pytest

from app.models.runtime import AgentRunUsage
from app.runtime.llm.client import LLMResponse
from app.runtime.orchestration.finance_runtime import FinanceRuntime
from tests.cfo_decision_fakes import execute

TRANSACTIONS = [
    {"date": "2026-06-10", "month": "2026-06", "description": "房租",
     "counterparty": "房东", "amount": -7000.0, "category": "housing", "is_duplicate": False},
]
MONTHLY_TOTALS = [{"month": "2026-06", "income": 12628.8, "expense": 19433.92, "net": -6805.12}]


class FakeDeepSeek:
    def __init__(self, reply="Grounded LLM reply.", fail=False):
        self.reply = reply
        self.fail = fail
        self.calls: list[dict] = []

    def available(self, profile="chat"):
        return True

    async def generate_text(self, prompt, *, profile="chat", system=""):
        self.calls.append({"prompt": prompt, "system": system, "profile": profile})
        if self.fail:
            raise TimeoutError("provider timeout")
        return LLMResponse(
            content=self.reply,
            usage=AgentRunUsage(request_count=1, input_tokens=800, output_tokens=120, total_tokens=920),
            model_name="deepseek-chat",
        )


class UnavailableClient:
    def available(self, profile="chat"):
        return False


class StreamingFakeDeepSeek(FakeDeepSeek):
    def __init__(self, reply):
        super().__init__(reply=reply)
        self.stream_calls = 0

    async def generate_text_stream(
        self, prompt, *, profile="chat", system="", on_delta=None
    ):
        self.stream_calls += 1
        if on_delta is not None:
            await on_delta(self.reply)
        return await self.generate_text(prompt, profile=profile, system=system)


async def _run(client, message="帮我分析这个月消费"):
    runtime = FinanceRuntime(
        llm_client=client,
        decision_engine=execute("finance.expense_review"),
    )
    return await runtime.handle(
        user_id="demo",
        message=message,
        profile={},
        transactions=TRANSACTIONS,
        monthly_totals=MONTHLY_TOTALS,
        chat_history=[{"role": "user", "content": "之前的问题"}],
        memory_context={},
    )


def _patch_investment_research(monkeypatch, saved_records):
    from app.runtime.orchestration import finance_runtime

    class FakeResearchService:
        def get_instrument_research(self, *args, **kwargs):
            return object()

    monkeypatch.setattr(
        finance_runtime,
        "get_investment_research_service",
        lambda: FakeResearchService(),
    )
    monkeypatch.setattr(
        finance_runtime,
        "project_instrument_research",
        lambda snapshot: {
            "status": "available",
            "symbol": "AAPL",
            "asset_type": "equity",
            "profile": {"currency": "USD", "source": "openbb:yfinance"},
            "quote": {
                "price": {"amount": "210.50", "currency": "USD"},
                "quote_as_of": "2026-07-18T20:00:00Z",
                "source": "openbb:yfinance",
            },
            "history": {
                "date_from": "2026-04-20",
                "date_to": "2026-07-18",
                "bar_count": 62,
                "change_percent": "4.25",
                "source": "openbb:yfinance",
            },
            "performance": {"status": "available", "period_return_percent": "4.25"},
            "benchmark": {"status": "available", "benchmark_symbol": "SPY"},
            "readiness": {
                "status": "ready",
                "reporting_currency": "CNY",
                "findings": [],
                "limitations": [],
            },
            "evidence": [
                {
                    "kind": "quote",
                    "source": "openbb:yfinance",
                    "as_of": "2026-07-18T20:00:00Z",
                    "description": "End-of-day market quote",
                }
            ],
            "limitations": [],
            "trade_actions_allowed": False,
        },
    )
    monkeypatch.setattr(finance_runtime, "list_latest_quality_reports_db", lambda _: [])
    monkeypatch.setattr(finance_runtime, "write_session_context", lambda **_: None)
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )


@pytest.mark.asyncio
class TestLLMCompose:
    async def test_llm_reply_replaces_template(self):
        client = FakeDeepSeek(reply="六月房租是最大支出，建议关注弹性类目。")

        result = await _run(client)

        assert result["reply"] == "六月房租是最大支出，建议关注弹性类目。"
        assert len(client.calls) == 1

    async def test_prompt_carries_evidence_and_history(self):
        client = FakeDeepSeek()

        await _run(client, message="6月房租多少")

        call = client.calls[0]
        assert "expense_snapshot" in call["prompt"]
        assert "audit" in call["prompt"]
        assert "之前的问题" in call["prompt"]  # recent turns included
        assert "never invent numbers" in call["system"]

    async def test_provider_failure_falls_back_to_template(self):
        client = FakeDeepSeek(fail=True)

        result = await _run(client)

        assert "CFO" in result["reply"]  # deterministic template survived
        assert result["data"]["audit"] is not None

    async def test_unavailable_client_skips_llm(self):
        result = await _run(UnavailableClient())

        assert "CFO" in result["reply"]

    async def test_data_contract_untouched_by_llm(self):
        client = FakeDeepSeek(reply="LLM reply")

        result = await _run(client)

        # LLM only rewrites the reply text; typed data blocks stay intact.
        assert result["data"]["summary_cards"]
        assert result["data"]["audit"]["status"] in ("verified", "needs_review", "data_limited")
        assert result["request_id"]

    async def test_investment_reply_is_buffered_and_unsafe_output_is_blocked(
        self, monkeypatch
    ):
        saved_records = []
        _patch_investment_research(monkeypatch, saved_records)
        client = StreamingFakeDeepSeek(
            reply="Buy AAPL now for a guaranteed return."
        )
        deltas = []

        async def on_delta(text):
            deltas.append(text)

        runtime = FinanceRuntime(
            llm_client=client,
            decision_engine=execute("investment.research_review"),
        )
        result = await runtime.handle(
            user_id="demo",
            message="Should I buy stock AAPL?",
            profile={},
            transactions=[],
            monthly_totals=[],
            chat_history=[],
            memory_context={},
            on_reply_delta=on_delta,
        )

        assert client.stream_calls == 0
        assert "Buy AAPL" not in result["reply"]
        assert "guaranteed return" not in result["reply"]
        assert deltas == [result["reply"]]
        guard = saved_records[0].policy["investment_output_guard"]
        assert guard == {
            "status": "blocked",
            "violations": ["trade_instruction", "return_guarantee"],
        }
        assert saved_records[0].policy["llm_usage_by_stage"]["llm_compose"][
            "status"
        ] == "policy_blocked"
