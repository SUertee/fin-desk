"""
Health check and schema endpoints.
"""

from functools import lru_cache

from fastapi import APIRouter

from app.connectors.cache.redis_cache import redis_cache_status
from app.runtime.execution.finance_turn_executor import (
    SPECIALIST_TOOL_BY_AGENT,
)
from app.runtime.orchestration.factory import build_finance_runtime

router = APIRouter()


@lru_cache(maxsize=1)
def _self_hosted_tool_names() -> tuple[str, ...]:
    """Resolve once from the actual chat runtime registry to prevent drift."""

    runtime = build_finance_runtime()
    return tuple(spec.name for spec in runtime.tool_registry.available())


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "architecture": "cfo_first",
        "agent_runtime": "self_hosted_cfo_agent",
        "user_facing_agent": "cfo",
        "controlled_tools": list(_self_hosted_tool_names()),
        "specialist_agent_tools": list(SPECIALIST_TOOL_BY_AGENT.values()),
        "capabilities": {
            "investment_research": "read_only",
            "hypothetical_scenarios": True,
            "trade_execution": False,
        },
        "cache": {
            "provider": "redis",
            "status": redis_cache_status(),
            "durable_source": "postgresql",
        },
        "runtime_components": [
            "orchestration.finance_runtime",
            "agents.cfo.decision",
            "capabilities.catalog",
            "capabilities.resolver",
            "policy.runtime_policy",
            "policy.audit_runner",
            "specialists.investment_research",
            "connectors.market_data",
            "connectors.exchange_rates",
            "costing.service",
            "observability.trace_collector",
            "observability.run_observer",
            "contracts.output_validation",
            "response.response_composer",
            "evals.replay",
        ],
    }
