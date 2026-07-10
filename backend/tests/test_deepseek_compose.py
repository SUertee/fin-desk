"""LLM-composed CFO reply tests (fake DeepSeek client, fully offline)."""

import pytest

from app.models.runtime import AgentRunUsage
from app.runtime.llm.client import LLMResponse
from app.runtime.orchestration.finance_runtime import FinanceRuntime

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
            usage=AgentRunUsage(requests=1, input_tokens=800, output_tokens=120, total_tokens=920),
            model_name="deepseek-chat",
        )


class UnavailableClient:
    def available(self, profile="chat"):
        return False


async def _run(client, message="帮我分析这个月消费"):
    runtime = FinanceRuntime(llm_client=client)
    return await runtime.handle(
        user_id="demo",
        message=message,
        profile={},
        transactions=TRANSACTIONS,
        monthly_totals=MONTHLY_TOTALS,
        chat_history=[{"role": "user", "content": "之前的问题"}],
        memory_context={},
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
