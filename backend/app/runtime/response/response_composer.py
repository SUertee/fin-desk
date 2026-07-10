"""Stable response composition for CFO-owned chat replies."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.models.agent_data import (
    AgentAction,
    AgentAudit,
    AgentFinding,
    FinanceAgentData,
    SummaryCard,
    normalize_finance_agent_data,
)


def _normalize_audit(value: object) -> AgentAudit | None:
    if isinstance(value, AgentAudit):
        return value
    if isinstance(value, dict):
        raw_audit = value.get("audit", value)
        try:
            return AgentAudit.model_validate(raw_audit)
        except ValidationError:
            return None
    return None


def _with_audit_repair(
    data: FinanceAgentData | None,
    audit_repair: object | None,
) -> FinanceAgentData | None:
    audit = _normalize_audit(audit_repair)
    if audit is None:
        return data
    if data is None:
        return FinanceAgentData(audit=audit)
    if data.audit is not None:
        return data
    return data.model_copy(update={"audit": audit})


def compose_runtime_response(
    raw_result: dict[str, Any],
    *,
    default_agent: str = "general",
    audit_repair: object | None = None,
) -> dict[str, Any]:
    reply = (
        raw_result.get("reply")
        or raw_result.get("final_reply")
        or raw_result.get("agent_reply")
        or ""
    )
    data = normalize_finance_agent_data(
        raw_result.get("data") or raw_result.get("agent_data")
    )
    data = _with_audit_repair(data, audit_repair)
    return {
        "reply": reply,
        "agent_used": raw_result.get("agent_used") or default_agent,
        "data": data,
    }


def compose_finance_chat_response(
    *,
    reply: str,
    summary_cards: list[SummaryCard],
    findings: list[AgentFinding],
    actions: list[AgentAction],
    audit: AgentAudit,
) -> dict[str, Any]:
    """Compose the stable ChatResponse payload returned by FinanceRuntime."""

    return {
        "reply": reply,
        "agent_used": "cfo",
        "data": {
            "summary_cards": [item.model_dump(mode="json") for item in summary_cards],
            "findings": [item.model_dump(mode="json") for item in findings],
            "actions": [item.model_dump(mode="json") for item in actions],
            "audit": audit.model_dump(mode="json"),
        },
    }
