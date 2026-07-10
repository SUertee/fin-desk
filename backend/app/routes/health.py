"""
Health check and schema endpoints.
"""

from fastapi import APIRouter

from app.agents.specialists import OPENAI_SPECIALIST_TOOL_NAMES
from app.services.schema import FINANCE_ANALYSIS_SCHEMA
from app.tools.openai_finance_tools import OPENAI_FINANCE_TOOL_NAMES

router = APIRouter()


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
        "controlled_tools": OPENAI_FINANCE_TOOL_NAMES,
        "specialist_agent_tools": OPENAI_SPECIALIST_TOOL_NAMES,
        "runtime_components": [
            "team.finance_team_runtime",
            "providers.openai_cfo_runtime",
            "providers.openai_analysis_runtime",
            "harness.agent_contracts",
            "policy.runtime_policy",
            "policy.audit_runner",
            "policy.cost_policy",
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
