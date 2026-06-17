"""OpenAI Agents SDK runtime for CFO-first finance chat."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from app.agents.cfo.agent import build_cfo_agent
from app.runtime.response_composer import compose_runtime_response
from app.tools.audit_tools import build_audit_review
from app.tools.openai_finance_tools import build_openai_finance_tools
from app.tools.specialist_tools import build_controlled_specialist_payloads


AgentFactory = Callable[[list[Any] | None], Any]
ToolBuilder = Callable[[dict[str, Any]], list[Any]]


def _load_runner() -> Any:
    try:
        from agents import Runner
    except Exception as exc:
        raise RuntimeError("openai-agents package is not installed") from exc
    return Runner


def _parse_embedded_json(reply: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, character in enumerate(reply):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(reply[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _build_cfo_input(context: dict[str, Any]) -> str:
    payload = {
        "user_message": context.get("message", ""),
        "runtime_policy": context.get("runtime_policy", {}),
        "profile": context.get("profile", {}),
        "expense_snapshot": context.get("expense_snapshot", {}),
        "budget_snapshot": context.get("budget_snapshot", {}),
        "monthly_totals": context.get("monthly_totals", []),
        "transactions_sample": context.get("transactions_sample", []),
        "recent_chat_history": context.get("chat_history", []),
    }
    return (
        "Answer this personal finance request as the CFO agent. Use tools when "
        "they improve evidence quality. Keep the final answer user-facing and "
        "include a compact JSON block only when structured insights are useful.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


class OpenAICFORuntime:
    def __init__(
        self,
        *,
        runner: Any | None = None,
        agent_factory: AgentFactory = build_cfo_agent,
        tool_builder: ToolBuilder = build_openai_finance_tools,
    ):
        self.runner = runner
        self.agent_factory = agent_factory
        self.tool_builder = tool_builder

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        if self.runner is None and not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI Agents SDK runtime")

        tools = self.tool_builder(context)
        agent = self.agent_factory(tools)
        runner = self.runner or _load_runner()
        max_turns = int(os.getenv("OPENAI_AGENT_MAX_TURNS", "6"))
        result = await runner.run(agent, _build_cfo_input(context), max_turns=max_turns)

        final_output = getattr(result, "final_output", "")
        if not isinstance(final_output, str):
            final_output = str(final_output)

        return compose_runtime_response(
            {
                "reply": final_output,
                "agent_used": "cfo",
                "data": _parse_embedded_json(final_output),
            },
            default_agent="cfo",
            audit_repair=build_audit_review(
                context,
                build_controlled_specialist_payloads(context),
            ),
        )
