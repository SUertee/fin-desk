"""Expense Analyst specialist: deterministic spending review over snapshots."""

from __future__ import annotations

from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistFinding,
    SpecialistInput,
    SpecialistRecommendation,
)


def run(input: SpecialistInput) -> SpecialistAgentOutput:
    zh = input.evidence.get("reply_language") == "zh"
    snapshot = input.evidence.get("expense_snapshot", {})
    top_categories = snapshot.get("top_categories") or []
    anomalies = snapshot.get("anomalies") or []
    findings: list[SpecialistFinding] = []
    recommendations: list[SpecialistRecommendation] = []
    limitations: list[str] = []

    if top_categories:
        top = top_categories[0]
        category = top.get("category", "Top category")
        findings.append(
            SpecialistFinding(
                title=(
                    f"{category} 是最大的支出类目" if zh
                    else f"{category} is the largest spend area"
                ),
                evidence=[
                    f"{category} 合计 {top.get('amount')}。" if zh
                    else f"{category} totals {top.get('amount')}."
                ],
                risk_level="medium" if float(top.get("amount") or 0) > 0 else "low",
            )
        )
        recommendations.append(
            SpecialistRecommendation(
                title="审查最大的弹性支出类目" if zh else "Review the largest flexible category",
                rationale=(
                    "最快的可控节流通常来自最大的经常性类目。" if zh
                    else "The fastest controllable savings usually come from the largest recurring category."
                ),
                next_step=(
                    "选定一个头部类目，在下次导入账单前设一个周上限。" if zh
                    else "Pick one top category and set a weekly cap before the next statement import."
                ),
            )
        )
    else:
        limitations.append("没有可用的支出分类数据。" if zh else "No spending categories were available.")

    if anomalies:
        findings.append(
            SpecialistFinding(
                title="有潜在异常交易需要复核" if zh else "Potential unusual transactions need review",
                evidence=[
                    f"在已加载交易中检测到 {len(anomalies)} 笔异常候选。" if zh
                    else f"{len(anomalies)} anomaly candidates were detected in the loaded transaction set."
                ],
                risk_level="medium",
            )
        )

    if not int(snapshot.get("transaction_count") or 0):
        limitations.append(
            "没有可用于支出分析的有效交易。" if zh
            else "No active transactions were available for expense analysis."
        )

    quality = input.evidence.get("import_quality") or {}
    for report in quality.get("reports", []):
        if report.get("duplicate_count"):
            limitations.append(
                (
                    f"{report.get('source_type', 'import')} 数据已排除 "
                    f"{report['duplicate_count']} 笔跨源重复。"
                )
                if zh
                else (
                    f"{report.get('source_type', 'import')} data excludes "
                    f"{report['duplicate_count']} cross-source duplicate rows."
                )
            )
        confidence_share = report.get("category_confidence")
        if confidence_share is not None and confidence_share < 0.6:
            limitations.append(
                (
                    f"{report.get('source_type', '导入')} 中仅 {round(confidence_share * 100)}% "
                    "的交易有可信分类，分类统计可能偏低。"
                )
                if zh
                else (
                    f"Only {round(confidence_share * 100)}% of "
                    f"{report.get('source_type', 'imported')} rows have a confident "
                    "category; spending breakdowns may under-report."
                )
            )

    return SpecialistAgentOutput(
        specialist="expense_analyst",
        confidence=0.78 if snapshot.get("transaction_count") else 0.35,
        findings=findings,
        recommendations=recommendations,
        limitations=limitations,
    )
