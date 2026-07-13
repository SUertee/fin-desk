"""Usage helpers for provider adapters."""

from __future__ import annotations

from app.models.runtime import AgentRunUsage


def empty_usage() -> AgentRunUsage:
    return AgentRunUsage()


def usage_from_response(usage_obj) -> AgentRunUsage:
    """Normalize a provider usage object into AgentRunUsage.

    One request was made either way; a missing usage payload safely yields
    zero tokens instead of raising.
    """

    return AgentRunUsage(
        request_count=1,
        model_response_count=1 if usage_obj is not None else 0,
        input_tokens=getattr(usage_obj, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage_obj, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage_obj, "total_tokens", 0) or 0,
    )
