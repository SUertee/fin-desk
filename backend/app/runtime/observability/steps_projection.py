"""User-level steps projection of a run's pipeline.

Maps recorded tool calls and handoffs onto friendly labels for the
"CFO 已完成 N 步分析" block. Never exposes payloads or latency.
"""

from __future__ import annotations

from typing import Any

TOOL_LABELS = {
    "get_finance_context": "读取财务上下文",
    "get_expense_snapshot": "汇总支出结构",
    "get_budget_snapshot": "评估预算状态",
    "get_anomaly_summary": "检查异常交易",
    "get_cashflow_summary": "汇总现金流",
    "get_import_quality_report": "核对数据质量",
    "query_transactions": "查询账本明细",
}

SPECIALIST_LABELS = {
    "expense_analyst": "Expense Analyst 分析",
    "budget_coach": "Budget Coach 评估",
    "auditor": "审计复核",
    "market_context": "市场背景检索",
}

# Plumbing that would read as noise to a user
_HIDDEN_TOOLS = {"llm_compose"}
_SPECIALIST_TOOL_NAMES = {
    "consult_expense_analyst",
    "consult_budget_coach",
    "consult_auditor",
    "consult_market_context",
}


def project_steps(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Project a run record into ordered user-facing steps."""

    steps: list[dict[str, Any]] = []
    for tool_call in record.get("tool_calls") or []:
        name = str(tool_call.get("name") or "")
        status = tool_call.get("status")
        if name in _HIDDEN_TOOLS or name in _SPECIALIST_TOOL_NAMES:
            continue
        if status not in ("called", "failed"):
            continue
        steps.append(
            {
                "label": TOOL_LABELS.get(name, name),
                "kind": "tool",
                "done": status == "called",
            }
        )
    for handoff in record.get("handoffs") or []:
        to_agent = str(handoff.get("to_agent") or "")
        kind = "audit" if to_agent == "auditor" else "specialist"
        steps.append(
            {
                "label": SPECIALIST_LABELS.get(to_agent, f"{to_agent} 分析"),
                "kind": kind,
                "done": handoff.get("status") == "completed",
            }
        )
    return steps
