from app.models.runtime import AgentRunUsage
from app.runtime.policy.cost_policy import estimate_run_cost, model_name_for_entrypoint


def test_cost_policy_uses_deepseek_profile_rates(monkeypatch):
    # Profile rates (model_profiles.yaml) take precedence over env rates.
    monkeypatch.setenv("OPENAI_AGENT_INPUT_COST_PER_1M", "99.0")
    monkeypatch.setenv("OPENAI_AGENT_OUTPUT_COST_PER_1M", "99.0")

    cost = estimate_run_cost(
        entrypoint="chat",
        usage=AgentRunUsage(input_tokens=1_000_000, output_tokens=1_000_000),
    )

    assert cost.input_cost_per_1m == 0.07
    assert cost.output_cost_per_1m == 0.28
    assert cost.estimated_total_cost == 0.35
    assert cost.pricing_source == "env_per_1m_tokens"


def test_model_name_defaults_to_profile_model(monkeypatch):
    monkeypatch.delenv("OPENAI_AGENT_MODEL", raising=False)

    assert model_name_for_entrypoint("chat") == "deepseek-chat"


def test_model_name_env_override_still_wins(monkeypatch):
    monkeypatch.setenv("OPENAI_AGENT_MODEL", "gpt-test")

    assert model_name_for_entrypoint("chat") == "gpt-test"


def test_model_name_for_analyze_prefers_analysis_model(monkeypatch):
    monkeypatch.setenv("OPENAI_AGENT_MODEL", "gpt-agent")
    monkeypatch.setenv("OPENAI_ANALYSIS_MODEL", "gpt-analysis")

    assert model_name_for_entrypoint("analyze") == "gpt-analysis"
