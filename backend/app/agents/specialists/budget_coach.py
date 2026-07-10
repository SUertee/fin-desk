"""Budget Coach specialist: deterministic budget guidance from snapshots."""

from __future__ import annotations

from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistFinding,
    SpecialistInput,
    SpecialistRecommendation,
)


def run(input: SpecialistInput) -> SpecialistAgentOutput:
    zh = input.evidence.get("reply_language") == "zh"
    snapshot = input.evidence.get("budget_snapshot", {})
    status = str(snapshot.get("status") or "data_limited")
    expense_ratio = snapshot.get("expense_ratio")
    limitations: list[str] = []

    if expense_ratio is None:
        limitations.append(
            "缺少月收入，无法计算支出比。" if zh
            else "Monthly income is missing, so expense ratio cannot be calculated."
        )

    if status == "risk":
        title = "立即压缩非必要支出" if zh else "Reduce non-essential spending immediately"
        rationale = "相对设定收入，当前支出偏高。" if zh else "Loaded expenses are high relative to configured income."
        next_step = (
            "冻结一个弹性类目 7 天，再复核现金流。" if zh
            else "Freeze one discretionary category for 7 days and re-check cash flow."
        )
        risk_level = "high"
    elif status == "watch":
        title = "设一个更紧的弹性支出护栏" if zh else "Set a tighter flexible-spending guardrail"
        rationale = "支出比偏高但仍可控。" if zh else "Expense ratio is elevated but still manageable."
        next_step = (
            "给最大的弹性类目设一个周上限。" if zh
            else "Create a weekly category cap for the largest flexible spend area."
        )
        risk_level = "medium"
    elif status == "good":
        title = "保持当前预算节奏" if zh else "Maintain current budget pace"
        rationale = "相对收入，当前支出可控。" if zh else "Loaded expenses appear controlled relative to income."
        next_step = (
            "在增加弹性消费前先自动转存储蓄。" if zh
            else "Automate a savings transfer before adding discretionary spend."
        )
        risk_level = "low"
    else:
        title = "补全收入与固定支出档案" if zh else "Complete income and recurring-expense profile"
        rationale = (
            "精确预算需要稳定的收入与固定支出输入。" if zh
            else "A precise budget requires stable income and recurring cost inputs."
        )
        next_step = (
            "在设置中补全月收入与固定月支出。" if zh
            else "Update profile income and monthly fixed expenses in Settings/Profile."
        )
        risk_level = "medium"

    status_label = {
        "good": "良好", "watch": "观察", "risk": "风险", "data_limited": "数据不足"
    }.get(status, status) if zh else status

    return SpecialistAgentOutput(
        specialist="budget_coach",
        confidence=0.8 if expense_ratio is not None else 0.45,
        findings=[
            SpecialistFinding(
                title=f"预算状态：{status_label}" if zh else f"Budget status is {status}",
                evidence=[
                    (f"支出比：{expense_ratio}" if zh else f"Expense ratio: {expense_ratio}")
                    if expense_ratio is not None
                    else ("支出比不可用。" if zh else "Expense ratio unavailable.")
                ],
                risk_level=risk_level,
            )
        ],
        recommendations=[
            SpecialistRecommendation(
                title=title,
                rationale=rationale,
                next_step=next_step,
            )
        ],
        limitations=limitations,
    )
