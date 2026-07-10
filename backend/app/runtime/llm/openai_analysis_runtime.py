"""OpenAI Agents SDK adapter for the `/analyze` endpoint."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from pydantic import BaseModel

from app.agents.specialists.analysis_agent import build_analysis_agent
from app.models.analysis import AnalysisAgentOutput
from app.runtime.observability.run_observer import (
    HarnessRunHooks,
    extract_run_observations,
    merge_run_observations,
)


AgentFactory = Callable[[list[Any] | None], Any]


def _load_runner() -> Any:
    try:
        from agents import Runner
    except Exception as exc:
        raise RuntimeError("openai-agents package is not installed") from exc
    return Runner


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        return stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return stripped


def _parse_json_output(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(_strip_json_fence(content))
    except json.JSONDecodeError as exc:
        raise ValueError("Analysis agent returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Analysis agent output must be a JSON object")
    return parsed


def _final_output_to_dict(final_output: Any) -> dict[str, Any]:
    if isinstance(final_output, AnalysisAgentOutput):
        return final_output.model_dump(mode="json")
    if isinstance(final_output, BaseModel):
        return final_output.model_dump(mode="json")
    if isinstance(final_output, dict):
        return final_output
    if isinstance(final_output, str):
        return _parse_json_output(final_output)
    raise ValueError("Analysis agent output must be a JSON object")


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"Analysis agent field `{field_name}` must be a list")
    return [str(item) for item in value]


def _normalize_analysis_output(output: dict[str, Any]) -> dict[str, Any]:
    budget = output.get("budget")
    if not isinstance(budget, dict):
        raise ValueError("Analysis agent field `budget` must be an object")

    notes = output.get("notes", "")
    if notes is None:
        notes = ""

    return {
        "insights": _string_list(output.get("insights"), "insights"),
        "actions": _string_list(output.get("actions"), "actions"),
        "budget": budget,
        "notes": str(notes),
    }


def _build_analysis_input(context: dict[str, Any]) -> str:
    payload = {
        "task": "Generate the JSON body for the /analyze response.",
        "required_output_keys": ["insights", "actions", "budget", "notes"],
        "evidence": context,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


class OpenAIAnalysisRuntime:
    def __init__(
        self,
        *,
        runner: Any | None = None,
        agent_factory: AgentFactory = build_analysis_agent,
    ):
        self.runner = runner
        self.agent_factory = agent_factory

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        if self.runner is None and not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI Agents SDK runtime")

        agent = self.agent_factory([])
        runner = self.runner or _load_runner()
        max_turns = int(
            os.getenv("OPENAI_ANALYSIS_MAX_TURNS")
            or os.getenv("OPENAI_AGENT_MAX_TURNS", "4")
        )
        hooks = HarnessRunHooks()
        result = await runner.run(
            agent,
            _build_analysis_input(context),
            max_turns=max_turns,
            hooks=hooks,
        )

        final_output = getattr(result, "final_output", "")
        analysis = _normalize_analysis_output(_final_output_to_dict(final_output))
        analysis["_run_observations"] = merge_run_observations(
            extract_run_observations(result),
            hooks.observations,
        )
        return analysis
