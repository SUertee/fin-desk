from types import SimpleNamespace

import pytest

from app.models.analysis import AnalysisAgentOutput
from app.runtime.llm.openai_analysis_runtime import OpenAIAnalysisRuntime


CONTEXT = {
    "user_id": "demo",
    "monthly_totals": [{"month": "2026-06", "net": 2400}],
    "category_summary": {"dining": {"total": 320}},
    "anomalies": [{"description": "Large dinner", "amount": -240}],
    "transactions_sample": [{"description": "Cafe", "amount": -12}],
}


@pytest.mark.asyncio
async def test_analysis_runtime_requires_api_key_without_injected_runner(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = OpenAIAnalysisRuntime(agent_factory=lambda tools: "agent")

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        await runtime.run(CONTEXT)


@pytest.mark.asyncio
async def test_analysis_runtime_uses_injected_runner_and_normalizes_output(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeRunner:
        async def run(self, agent, user_input, max_turns, hooks):
            assert agent == "analysis-agent"
            assert max_turns == 4
            assert hooks is not None
            assert "Generate the JSON body" in user_input
            assert "Large dinner" in user_input
            return SimpleNamespace(
                final_output=(
                    '{"insights": ["Dining is elevated"], '
                    '"actions": ["Set a dining cap"], '
                    '"budget": {"rules": ["Cap dining"], "monthly_targets": {"dining": 250}}, '
                    '"notes": ""}'
                ),
                context_wrapper=SimpleNamespace(
                    usage=SimpleNamespace(
                        requests=1,
                        input_tokens=60,
                        output_tokens=20,
                        total_tokens=80,
                    )
                ),
            )

    runtime = OpenAIAnalysisRuntime(
        runner=FakeRunner(),
        agent_factory=lambda tools: "analysis-agent",
    )

    result = await runtime.run(CONTEXT)

    assert result["insights"] == ["Dining is elevated"]
    assert result["actions"] == ["Set a dining cap"]
    assert result["budget"]["monthly_targets"]["dining"] == 250
    assert result["notes"] == ""
    assert result["_run_observations"].usage.total_tokens == 80


@pytest.mark.asyncio
async def test_analysis_runtime_accepts_fenced_json_from_model(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeRunner:
        async def run(self, agent, user_input, max_turns, hooks):
            assert hooks is not None
            return SimpleNamespace(
                final_output=(
                    '```json\n'
                    '{"insights": [], "actions": [], "budget": {}, "notes": "limited"}'
                    "\n```"
                )
            )

    runtime = OpenAIAnalysisRuntime(
        runner=FakeRunner(),
        agent_factory=lambda tools: "analysis-agent",
    )

    result = await runtime.run(CONTEXT)
    observations = result.pop("_run_observations")

    assert result == {
        "insights": [],
        "actions": [],
        "budget": {},
        "notes": "limited",
    }
    assert observations.usage.total_tokens == 0


@pytest.mark.asyncio
async def test_analysis_runtime_accepts_typed_agent_output(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeRunner:
        async def run(self, agent, user_input, max_turns, hooks):
            assert hooks is not None
            return SimpleNamespace(
                final_output=AnalysisAgentOutput(
                    insights=["Dining is elevated"],
                    actions=["Set a dining cap"],
                    budget={
                        "rules": ["Cap dining"],
                        "monthly_targets": {"dining": 250},
                    },
                    notes="",
                )
            )

    runtime = OpenAIAnalysisRuntime(
        runner=FakeRunner(),
        agent_factory=lambda tools: "analysis-agent",
    )

    result = await runtime.run(CONTEXT)

    assert result["insights"] == ["Dining is elevated"]
    assert result["budget"]["monthly_targets"]["dining"] == 250


@pytest.mark.asyncio
async def test_analysis_runtime_rejects_invalid_json(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeRunner:
        async def run(self, agent, user_input, max_turns, hooks):
            assert hooks is not None
            return SimpleNamespace(final_output="not json")

    runtime = OpenAIAnalysisRuntime(
        runner=FakeRunner(),
        agent_factory=lambda tools: "analysis-agent",
    )

    with pytest.raises(ValueError, match="invalid JSON"):
        await runtime.run(CONTEXT)
