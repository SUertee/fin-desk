"""Usage helpers for provider adapters."""

from __future__ import annotations

from app.models.runtime import AgentRunUsage


def empty_usage() -> AgentRunUsage:
    return AgentRunUsage()


def _value(item, name: str, default=0):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def usage_from_response(usage_obj) -> AgentRunUsage:
    """Normalize a provider usage object into AgentRunUsage.

    One request was made either way; a missing usage payload safely yields
    zero tokens instead of raising.
    """

    input_tokens = _value(usage_obj, "prompt_tokens", 0) or 0
    cache_hit = _value(usage_obj, "prompt_cache_hit_tokens", None)
    cache_miss = _value(usage_obj, "prompt_cache_miss_tokens", None)

    # OpenAI-compatible providers expose cache details in different shapes.
    # Normalize them here so the finance domain never depends on provider keys.
    if cache_hit is None:
        details = _value(usage_obj, "prompt_tokens_details", None)
        if details is not None:
            cache_hit = _value(details, "cached_tokens", 0) or 0
            cache_miss = max(input_tokens - cache_hit, 0)

    return AgentRunUsage(
        request_count=1,
        model_response_count=1 if usage_obj is not None else 0,
        input_tokens=input_tokens,
        cached_input_tokens=cache_hit or 0,
        uncached_input_tokens=cache_miss or 0,
        output_tokens=_value(usage_obj, "completion_tokens", 0) or 0,
        total_tokens=_value(usage_obj, "total_tokens", 0) or 0,
    )
