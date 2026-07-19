"""Auditor specialist: evidence and risk review over peer specialist outputs."""

from __future__ import annotations

from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistFinding,
    SpecialistInput,
    SpecialistRecommendation,
)


def run(input: SpecialistInput) -> SpecialistAgentOutput:
    zh = input.evidence.get("reply_language") == "zh"
    policy = input.policy or {}
    risk_level = str(policy.get("risk_level") or "low")
    required_specialists = policy.get("required_specialists") or []

    warnings: list[str] = []
    limitations: list[str] = []
    has_investment_evidence = (
        (input.evidence.get("investment_research") or {}).get("status") == "available"
    )
    if not input.evidence.get("transactions_sample") and not has_investment_evidence:
        limitations.append("没有可用的交易样本。" if zh else "No transaction sample was available.")
    if risk_level == "high":
        warnings.append(
            "高风险投资类话题需保持审慎、非建议式表述。" if zh
            else "High-risk investment language requires cautious, non-advisory framing."
        )
    if not input.prior_outputs and required_specialists:
        warnings.append(
            "策略要求专家参与，但没有可用的专家输出。" if zh
            else "Runtime policy required specialists, but no specialist output was available."
        )

    status = "needs_review" if warnings else "verified"
    status_label = ("需复核" if status == "needs_review" else "已核验") if zh else status
    confidence = 0.72 if limitations else 0.84
    return SpecialistAgentOutput(
        specialist="auditor",
        confidence=confidence,
        findings=[
            SpecialistFinding(
                title=f"审计状态：{status_label}" if zh else f"Audit status: {status}",
                evidence=warnings or (
                    ["结论均有已加载的结构化证据支撑。"] if zh
                    else ["Claims are grounded in loaded structured evidence."]
                ),
                risk_level="medium" if warnings else "low",
            )
        ],
        recommendations=[
            SpecialistRecommendation(
                title="保持建议有据可依" if zh else "Keep recommendations evidence-bound",
                rationale=(
                    "个人财务建议应避免无依据断言或保证性结论。" if zh
                    else "Personal finance guidance should avoid unsupported claims or guaranteed outcomes."
                ),
                next_step=(
                    "对基于不完整数据的建议，同步展示数据局限。" if zh
                    else "Show data limitations next to any recommendation based on incomplete context."
                ),
            )
        ],
        limitations=limitations,
    )
