import pytest

from agents import deep_agent_factory


def test_build_subagents_contains_finance_team_members():
    names = {subagent["name"] for subagent in deep_agent_factory.build_finance_subagents()}

    assert names == {
        "expense_analyst",
        "budget_coach",
        "auditor",
        "market_scout",
    }


def test_extract_text_reply_handles_deepagents_messages():
    result = {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "final answer"},
        ]
    }

    assert deep_agent_factory.extract_text_reply(result) == "final answer"


@pytest.mark.asyncio
async def test_invoke_finance_deep_agent_raises_clear_error_without_package(monkeypatch):
    monkeypatch.setattr(deep_agent_factory, "create_deep_agent", None)

    with pytest.raises(RuntimeError, match="deepagents package is not installed"):
        await deep_agent_factory.invoke_finance_deep_agent(
            {
                "message": "health check",
                "profile": {"name": "Demo"},
                "expense_snapshot": {},
                "budget_snapshot": {},
                "transactions_sample": [],
                "monthly_totals": [],
                "chat_history": [],
            }
        )
