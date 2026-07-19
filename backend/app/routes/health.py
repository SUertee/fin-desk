"""
Health check and schema endpoints.
"""

from functools import lru_cache

from fastapi import APIRouter

from app.agents.specialists import OPENAI_SPECIALIST_TOOL_NAMES
from app.runtime.orchestration.finance_runtime import (
    FinanceRuntime,
    SPECIALIST_TOOL_BY_AGENT,
)
from app.services.schema import FINANCE_ANALYSIS_SCHEMA
from app.tools.openai_finance_tools import OPENAI_FINANCE_TOOL_NAMES

router = APIRouter()


@lru_cache(maxsize=1)
def _self_hosted_tool_names() -> tuple[str, ...]:
    """Resolve once from the actual chat runtime registry to prevent drift."""

    runtime = FinanceRuntime()
    return tuple(spec.name for spec in runtime.tool_registry.available())


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "architecture": "cfo_first",
        # The runtime actually serving /chat; the SDK runtime only backs /analyze.
        "agent_runtime": "self_hosted_deterministic",
        "analysis_runtime": "openai_agents_sdk",
        "user_facing_agent": "cfo",
        "controlled_tools": list(_self_hosted_tool_names()),
        "specialist_agent_tools": list(SPECIALIST_TOOL_BY_AGENT.values()),
        "analysis_adapter_tools": [
            *OPENAI_FINANCE_TOOL_NAMES,
            *OPENAI_SPECIALIST_TOOL_NAMES,
        ],
        "capabilities": {
            "investment_research": "read_only",
            "hypothetical_scenarios": True,
            "trade_execution": False,
        },
        "runtime_components": [
            "team.finance_team_runtime",
            "providers.openai_cfo_runtime",
            "providers.openai_analysis_runtime",
            "harness.agent_contracts",
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


@router.get("/schema")
def schema():
    return FINANCE_ANALYSIS_SCHEMA
