from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agents.cfo.decision import CfoDecisionEngine
from app.models.chat import ChatRequest, ChatResponse
from app.models.runtime import AgentRunUsage
from app.runtime.orchestration.factory import build_finance_runtime


class FakeDecisionClient:
    def __init__(self, data):
        self.data = data
        self.prompt = ""
        self.system = ""

    def available(self, profile="router"):
        return True

    async def generate_json(self, prompt, *, profile="router", system=""):
        self.prompt = prompt
        self.system = system
        return SimpleNamespace(
            data=self.data,
            usage=AgentRunUsage(request_count=1, total_tokens=12),
            model_name="decision-model",
        )


def _capabilities():
    return tuple(
        item.descriptor
        for item in build_finance_runtime().capability_catalog.list()
        if item.status.enabled and item.status.available
    )


@pytest.mark.asyncio
async def test_model_selects_conversation_without_execution_fields():
    client = FakeDecisionClient(
        {"action": "direct_response", "reply": "你好，我可以帮你核对账本。", "capability_requests": []}
    )
    result = await CfoDecisionEngine(lambda: client).decide(
        "你好",
        capabilities=_capabilities(),
        chat_history=[],
        memory_context={},
        profile={},
        needs_clarification=False,
    )

    assert result.status == "called"
    assert result.decision.action == "direct_response"
    assert "execution path" not in client.prompt.lower()
    assert "execution paths" in client.system.lower()
    assert (
        "conversation context may resolve meaning but is never evidence"
        in client.system.lower()
    )
    assert "amounts, or percentages must use execute" in client.system.lower()


@pytest.mark.asyncio
async def test_execute_accepts_only_registered_capability_ids():
    client = FakeDecisionClient(
        {
            "action": "execute",
            "reply": None,
            "capability_requests": [{"capability_id": "finance.expense_review"}],
        }
    )
    result = await CfoDecisionEngine(lambda: client).decide(
        "分析我的支出",
        capabilities=_capabilities(),
        chat_history=[],
        memory_context={},
        profile={},
        needs_clarification=False,
    )

    assert result.status == "called"
    assert result.decision.capability_requests[0].capability_id == "finance.expense_review"

    client.data["capability_requests"] = [{"capability_id": "database.run_sql"}]
    rejected = await CfoDecisionEngine(lambda: client).decide(
        "删掉账本",
        capabilities=_capabilities(),
        chat_history=[],
        memory_context={},
        profile={},
        needs_clarification=False,
    )
    assert rejected.status == "invalid_output"
    assert rejected.decision is None


@pytest.mark.asyncio
async def test_invalid_shape_and_unavailable_provider_are_explicit():
    invalid = FakeDecisionClient(
        {"action": "execute", "reply": "先执行", "capability_requests": []}
    )
    invalid_result = await CfoDecisionEngine(lambda: invalid).decide(
        "分析",
        capabilities=_capabilities(),
        chat_history=[],
        memory_context={},
        profile={},
        needs_clarification=False,
    )
    assert invalid_result.status == "invalid_output"

    unavailable = await CfoDecisionEngine(lambda: None).decide(
        "你好",
        capabilities=_capabilities(),
        chat_history=[],
        memory_context={},
        profile={},
        needs_clarification=False,
    )
    assert unavailable.status == "unavailable"
    assert unavailable.decision is None


def test_chat_contract_rejects_caller_execution_and_ui_fields():
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "user_id": "demo",
                "message": "分析支出",
                "specialist_override": "expense_analyst",
            }
        )

    with pytest.raises(ValidationError):
        ChatResponse.model_validate(
            {
                "reply": "完成",
                "execution": {"outcome": "executed"},
                "ui_projection": {"mode": "analysis"},
            }
        )
