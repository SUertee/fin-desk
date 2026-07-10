"""Config-driven usage cost estimation for agent harness runs."""

from __future__ import annotations

import os
from typing import Iterable

from app.config.settings import get_settings, load_model_profiles
from app.models.runtime import AgentRunCost, AgentRunUsage, RuntimeEntrypoint


def _env_float(names: Iterable[str]) -> float | None:
    for name in names:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            continue
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if value >= 0 else None
    return None


def model_name_for_entrypoint(entrypoint: RuntimeEntrypoint) -> str:
    if entrypoint == "analyze":
        env_model = os.getenv("OPENAI_ANALYSIS_MODEL") or os.getenv("OPENAI_AGENT_MODEL")
    else:
        env_model = os.getenv("OPENAI_AGENT_MODEL")
    if env_model:
        return env_model

    settings = get_settings()
    profiles = load_model_profiles()
    if entrypoint == "analyze":
        profile = profiles.get(settings.analysis_model_profile)
    else:
        profile = profiles.get(settings.chat_model_profile)
    if profile is not None:
        return profile.model
    if entrypoint == "analyze":
        return "gpt-4o-mini"
    return "gpt-4o-mini"


def _input_rate_for_entrypoint(entrypoint: RuntimeEntrypoint) -> float | None:
    settings = get_settings()
    profiles = load_model_profiles()
    if entrypoint == "analyze":
        profile = profiles.get(settings.analysis_model_profile)
    else:
        profile = profiles.get(settings.chat_model_profile)
    if profile and profile.input_cost_per_1m is not None:
        return profile.input_cost_per_1m
    if settings.cost.input_cost_per_1m is not None:
        return settings.cost.input_cost_per_1m
    if entrypoint == "analyze":
        return _env_float(
            (
                "OPENAI_ANALYSIS_INPUT_COST_PER_1M",
                "OPENAI_AGENT_INPUT_COST_PER_1M",
                "OPENAI_INPUT_COST_PER_1M",
            )
        )
    return _env_float(("OPENAI_AGENT_INPUT_COST_PER_1M", "OPENAI_INPUT_COST_PER_1M"))


def _output_rate_for_entrypoint(entrypoint: RuntimeEntrypoint) -> float | None:
    settings = get_settings()
    profiles = load_model_profiles()
    if entrypoint == "analyze":
        profile = profiles.get(settings.analysis_model_profile)
    else:
        profile = profiles.get(settings.chat_model_profile)
    if profile and profile.output_cost_per_1m is not None:
        return profile.output_cost_per_1m
    if settings.cost.output_cost_per_1m is not None:
        return settings.cost.output_cost_per_1m
    if entrypoint == "analyze":
        return _env_float(
            (
                "OPENAI_ANALYSIS_OUTPUT_COST_PER_1M",
                "OPENAI_AGENT_OUTPUT_COST_PER_1M",
                "OPENAI_OUTPUT_COST_PER_1M",
            )
        )
    return _env_float(("OPENAI_AGENT_OUTPUT_COST_PER_1M", "OPENAI_OUTPUT_COST_PER_1M"))


def estimate_run_cost(
    *,
    entrypoint: RuntimeEntrypoint,
    usage: AgentRunUsage,
    model_name: str | None = None,
) -> AgentRunCost:
    input_rate = _input_rate_for_entrypoint(entrypoint)
    output_rate = _output_rate_for_entrypoint(entrypoint)
    currency = get_settings().cost.currency

    input_cost = 0.0
    output_cost = 0.0
    if input_rate is not None:
        input_cost = usage.input_tokens * input_rate / 1_000_000
    if output_rate is not None:
        output_cost = usage.output_tokens * output_rate / 1_000_000

    pricing_source = "env_per_1m_tokens" if input_rate is not None or output_rate is not None else "not_configured"

    return AgentRunCost(
        model_name=model_name or model_name_for_entrypoint(entrypoint),
        currency=currency,
        input_cost_per_1m=input_rate,
        output_cost_per_1m=output_rate,
        estimated_input_cost=round(input_cost, 8),
        estimated_output_cost=round(output_cost, 8),
        estimated_total_cost=round(input_cost + output_cost, 8),
        pricing_source=pricing_source,
    )
