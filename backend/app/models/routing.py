"""Public-safe conversation routing contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ConversationIntent = Literal[
    "small_talk",
    "acknowledgement",
    "finance_query",
    "follow_up",
    "evidence_request",
    "clarification",
    "unsupported",
]

ConversationExecutionPath = Literal[
    "light_reply",
    "cfo_analysis",
    "cfo_followup",
    "evidence_only",
    "clarification",
]

ConversationMemoryScope = Literal["none", "session", "finance_context"]
ConversationResponseMode = Literal[
    "light",
    "direct_answer",
    "analysis",
    "ask_clarification",
]


class ConversationRoute(BaseModel):
    """Safe route metadata that can be returned to the product UI.

    The router may keep private confidence/reasoning internally, but this
    contract only exposes behavior flags needed by the runtime and frontend.
    """

    intent: ConversationIntent
    execution_path: ConversationExecutionPath
    run_finance_pipeline: bool
    emit_steps: bool
    attach_evidence: bool
    memory_scope: ConversationMemoryScope = "none"
    response_mode: ConversationResponseMode
    label: str = ""
    ui_hints: dict[str, bool] = Field(default_factory=dict)


def build_route(
    intent: ConversationIntent,
    execution_path: ConversationExecutionPath,
    *,
    run_finance_pipeline: bool,
    emit_steps: bool,
    attach_evidence: bool,
    memory_scope: ConversationMemoryScope,
    response_mode: ConversationResponseMode,
    label: str = "",
) -> ConversationRoute:
    """Construct a route while keeping UI flags consistent."""

    return ConversationRoute(
        intent=intent,
        execution_path=execution_path,
        run_finance_pipeline=run_finance_pipeline,
        emit_steps=emit_steps,
        attach_evidence=attach_evidence,
        memory_scope=memory_scope,
        response_mode=response_mode,
        label=label,
        ui_hints={
            "show_process": emit_steps,
            "show_evidence_chips": attach_evidence,
            "structured_answer": response_mode == "analysis",
        },
    )


LIGHT_REPLY_ROUTE = build_route(
    "small_talk",
    "light_reply",
    run_finance_pipeline=False,
    emit_steps=False,
    attach_evidence=False,
    memory_scope="session",
    response_mode="light",
    label="light reply",
)
