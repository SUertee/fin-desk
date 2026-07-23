"""Per-run LLM usage/cost accounting across decision, intake, and compose.

One CFO run may spend tokens in up to three stages (turn_contextualize,
cfo_decide, llm_compose). The trace usage must be the SUM of all
stages — never the last stage overwriting the rest — and the run ledger
must expose a bounded per-stage projection at policy.llm_usage_by_stage.
"""

from types import SimpleNamespace

import pytest

from app.models.runtime import AgentRunUsage
from app.runtime.llm.client import LLMResponse
from app.runtime.orchestration import finance_runtime as fr
from app.runtime.orchestration.factory import build_finance_runtime
from tests.cfo_decision_fakes import execute


def _usage(input_tokens, output_tokens):
    return AgentRunUsage(
        request_count=1,
        model_response_count=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


class ThreeStageFakeLLM:
    """Serves the contextualizer, the CFO decision, and compose."""

    def __init__(self, *, contextualizer_data=None, decision_data=None):
        self.contextualizer_data = contextualizer_data or {
            "effective_message": "帮我盘一盘最近的情况",
            "resolution_status": "resolved",
            "resolved_slots": [],
            "confidence": 0.8,
        }
        self.decision_data = decision_data or {
            "action": "execute",
            "reply": None,
            "capability_requests": [
                {"capability_id": "finance.expense_review"}
            ],
        }

    def available(self, profile="chat"):
        return True

    async def generate_json(self, prompt, *, profile="router", system=""):
        if "Turn Contextualizer" in system:
            return SimpleNamespace(
                data=self.contextualizer_data,
                usage=_usage(10, 5),
                model_name="deepseek-v4-flash",
            )
        return SimpleNamespace(
            data=self.decision_data,
            usage=_usage(20, 10),
            model_name="deepseek-v4-flash",
        )

    async def generate_text(self, prompt, *, profile="chat", system=""):
        return LLMResponse(
            content="这是 CFO 的回复。",
            usage=_usage(40, 20),
            model_name="deepseek-v4-flash",
        )


async def _run(
    monkeypatch,
    llm_client,
    message,
    memory_context=None,
    decision_engine=None,
):
    records = []
    monkeypatch.setattr(
        fr, "save_agent_run_record_db", lambda record: records.append(record) or True
    )
    runtime = build_finance_runtime(
        decision_engine=decision_engine,
        llm_client=llm_client,
    )

    result = await runtime.handle(
        user_id="demo",
        message=message,
        profile={"name": "Demo", "monthly_income": 5000},
        transactions=[{"amount": -100, "category": "dining", "date": "2026-06-03"}],
        monthly_totals=[{"month": "2026-06", "net": 100}],
        chat_history=[{"role": "assistant", "content": "上一轮"}],
        memory_context=memory_context,
    )
    return result, records[0]


@pytest.mark.asyncio
async def test_three_stage_usage_accumulates_not_overwrites(monkeypatch):
    # "那个呢？" with no memory: deterministic resolver cannot resolve it, so
    # the model contextualizer rewrites it; the rewritten text is ambiguous
    # for execution, so the CFO decision runs; the pipeline then composes
    # with the LLM. Three billed stages in one run.
    result, record = await _run(monkeypatch, ThreeStageFakeLLM(), "那个呢？")

    assert result["reply"] == "这是 CFO 的回复。"
    # Sum of (10+5) + (20+10) + (40+20) — not the last stage's 60.
    assert record.usage.input_tokens == 70
    assert record.usage.output_tokens == 35
    assert record.usage.total_tokens == 105
    assert record.usage.request_count == 3
    assert record.usage.model_response_count == 3

    stages = record.policy["llm_usage_by_stage"]
    assert set(stages) == {"turn_contextualize", "cfo_decide", "llm_compose"}
    for name, entry in stages.items():
        assert entry["status"] == "called", name
        assert entry["model_name"] == "deepseek-v4-flash"
        assert entry["total_tokens"] > 0
        # metadata only — never prompts or histories
        assert set(entry) <= {
            "status", "latency_ms", "model_name", "profile",
            "request_count", "model_response_count",
            "input_tokens", "cached_input_tokens", "uncached_input_tokens",
            "output_tokens", "total_tokens",
        }
    assert stages["turn_contextualize"]["profile"] == "router"
    assert stages["llm_compose"]["profile"] == "chat"
    # All three appear in the tool timeline as well.
    tool_names = {c.name for c in record.tool_calls}
    assert {"turn_contextualize", "cfo_decide", "llm_compose"} <= tool_names
    assert record.cost.status == "complete"
    assert {stage.stage for stage in record.cost.stages} == {
        "turn_contextualize", "cfo_decide", "llm_compose"
    }
    assert record.cost.billing_totals[0].currency == "USD"
    assert str(record.cost.billing_totals[0].amount) == "0.000019600000"


@pytest.mark.asyncio
async def test_injected_decision_reports_zero_usage(monkeypatch):
    result, record = await _run(
        monkeypatch,
        None,
        "这个月购物支出占比多少？",
        decision_engine=execute("finance.expense_review"),
    )

    assert result["execution"]["outcome"] == "executed"
    assert record.usage.total_tokens == 0
    assert record.usage.request_count == 0
    stages = record.policy["llm_usage_by_stage"]
    assert set(stages) == {"cfo_decide"}
    assert stages["cfo_decide"]["status"] == "called"
    assert stages["cfo_decide"]["total_tokens"] == 0
    assert record.cost.status == "not_applicable"


@pytest.mark.asyncio
async def test_invalid_model_output_still_counts_billed_usage(monkeypatch):
    # Both model stages answer with contract-violating payloads. The output
    # is rejected (deterministic fallback), but the provider DID bill those
    # tokens — they must appear in the totals, flagged as invalid_output.
    llm = ThreeStageFakeLLM(
        contextualizer_data={"resolution_status": "run_pipeline"},
        decision_data={"action": "run_sql"},
    )
    result, record = await _run(monkeypatch, llm, "那个呢？")

    assert result["execution"]["outcome"] == "failed"
    stages = record.policy["llm_usage_by_stage"]
    assert stages["turn_contextualize"]["status"] == "invalid_output"
    assert stages["cfo_decide"]["status"] == "invalid_output"
    assert stages["turn_contextualize"]["total_tokens"] == 15
    assert stages["cfo_decide"]["total_tokens"] == 30
    # Usage accumulated from both rejected responses; no compose.
    assert record.usage.total_tokens == 45
    assert "llm_compose" not in stages
    assert record.cost.status == "complete"
    assert {stage.status for stage in record.cost.stages} == {"invalid_output"}


@pytest.mark.asyncio
async def test_provider_failure_adds_no_fake_usage(monkeypatch):
    class ExplodingLLM:
        def available(self, profile="chat"):
            return True

        async def generate_json(self, prompt, *, profile="router", system=""):
            raise TimeoutError("provider down")

        async def generate_text(self, prompt, *, profile="chat", system=""):
            raise TimeoutError("provider down")

    result, record = await _run(monkeypatch, ExplodingLLM(), "那个呢？")

    # Request returns an explicit failed decision without fabricating usage.
    assert result["execution"]["outcome"] == "failed"
    assert record.usage.total_tokens == 0
    stages = record.policy["llm_usage_by_stage"]
    assert stages["turn_contextualize"]["status"] == "failed"
    assert "total_tokens" not in stages["turn_contextualize"]
    assert record.cost.status == "not_applicable"
