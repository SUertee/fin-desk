"""
Health check and schema endpoints.
"""

from fastapi import APIRouter

from app.services.schema import FINANCE_ANALYSIS_SCHEMA

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "architecture": "cfo_first",
        "agent_runtime": "openai_agents_sdk",
        "user_facing_agent": "cfo",
        "controlled_tools": [
            "get_finance_context",
            "get_expense_snapshot",
            "get_budget_snapshot",
            "get_anomaly_summary",
            "get_cashflow_summary",
            "analyze_expense_patterns",
            "generate_budget_plan",
            "run_audit_review",
        ],
        "runtime_components": [
            "runtime_policy",
            "response_composer",
            "audit_runner",
        ],
    }


@router.get("/schema")
def schema():
    return FINANCE_ANALYSIS_SCHEMA
