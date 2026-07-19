"""Investment Research specialist over bounded, sourced market evidence."""

from __future__ import annotations

from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistFinding,
    SpecialistInput,
    SpecialistRecommendation,
)


READ_ONLY_LIMITATION = (
    "This review is read-only research, not individualized investment advice or a trade instruction."
)


def run(input: SpecialistInput) -> SpecialistAgentOutput:
    zh = input.evidence.get("reply_language") == "zh"
    research = input.evidence.get("investment_research") or {}
    status = str(research.get("status") or "unavailable")

    if status != "available":
        reason = str(research.get("reason") or "market evidence is unavailable")
        if status == "symbol_required":
            reason = "请提供明确的股票或 ETF 代码。" if zh else "Provide an explicit stock or ETF symbol."
        return SpecialistAgentOutput(
            specialist="investment_research",
            confidence=0.2,
            limitations=[reason, READ_ONLY_LIMITATION],
        )

    symbol = str(research.get("symbol") or "instrument")
    quote = research.get("quote") or {}
    history = research.get("history") or {}
    performance = research.get("performance") or {}
    benchmark = research.get("benchmark") or {}
    readiness = research.get("readiness") or {}
    profile = research.get("profile") or {}
    evidence = research.get("evidence") or []
    price = (quote.get("price") or {}).get("amount")
    currency = (quote.get("price") or {}).get("currency") or profile.get("currency") or ""
    quote_as_of = quote.get("quote_as_of")
    change = performance.get("period_return_percent", history.get("change_percent"))
    period = f"{history.get('date_from')} to {history.get('date_to')}"
    source_labels = sorted(
        {
            str(item.get("source"))
            for item in evidence
            if isinstance(item, dict) and item.get("source")
        }
    )

    findings: list[SpecialistFinding] = []
    if price is not None:
        findings.append(
            SpecialistFinding(
                title=(
                    f"{symbol} 最近行情为 {currency} {price}"
                    if zh
                    else f"{symbol} latest quote is {currency} {price}"
                ),
                evidence=[
                    (
                        f"行情时间：{quote_as_of}；来源：{quote.get('source')}"
                        if zh
                        else f"Quote as of {quote_as_of}; source: {quote.get('source')}"
                    )
                ],
                risk_level="medium",
            )
        )
    if change is not None:
        metric_evidence = [
            (
                f"区间：{period}；{history.get('bar_count')} 个日线数据点；来源：{history.get('source')}"
                if zh
                else f"Period: {period}; {history.get('bar_count')} daily bars; source: {history.get('source')}"
            )
        ]
        volatility = performance.get("annualized_volatility_percent")
        drawdown = performance.get("max_drawdown_percent")
        if volatility is not None:
            metric_evidence.append(
                f"年化波动率：{volatility}%"
                if zh
                else f"Annualized volatility: {volatility}%"
            )
        if drawdown is not None:
            metric_evidence.append(
                f"最大回撤：{drawdown}%"
                if zh
                else f"Maximum drawdown: {drawdown}%"
            )
        if benchmark.get("status") == "available":
            metric_evidence.append(
                (
                    f"相对 {benchmark.get('benchmark_symbol')} 的区间差：{benchmark.get('excess_period_return_percent')}%"
                    if zh
                    else f"Period difference versus {benchmark.get('benchmark_symbol')}: {benchmark.get('excess_period_return_percent')}%"
                )
            )
        findings.append(
            SpecialistFinding(
                title=(
                    f"观察期价格变化 {change}%"
                    if zh
                    else f"Observed price change is {change}%"
                ),
                evidence=metric_evidence,
                risk_level="medium",
            )
        )
    if readiness:
        readiness_status = str(readiness.get("status") or "insufficient_data")
        cash_flow = readiness.get("monthly_cash_flow")
        reserve_months = readiness.get("reserve_months")
        readiness_evidence = [
            (
                f"月度现金流：{cash_flow} {readiness.get('reporting_currency')}；流动储备：{reserve_months} 个月"
                if zh
                else f"Monthly cash flow: {cash_flow} {readiness.get('reporting_currency')}; liquid reserve: {reserve_months} months"
            )
        ]
        readiness_evidence.extend(
            str(item.get("title"))
            for item in readiness.get("findings") or []
            if isinstance(item, dict) and item.get("title")
        )
        findings.append(
            SpecialistFinding(
                title=(
                    f"投资准备状态：{readiness_status}"
                    if zh
                    else f"Investment readiness: {readiness_status}"
                ),
                evidence=readiness_evidence,
                risk_level="low" if readiness_status == "ready" else "high",
            )
        )
    if not findings:
        findings.append(
            SpecialistFinding(
                title=(
                    f"{symbol} 的资料已获取，但价格证据不完整"
                    if zh
                    else f"{symbol} profile is available but price evidence is incomplete"
                ),
                evidence=[
                    (f"来源：{', '.join(source_labels)}" if zh else f"Sources: {', '.join(source_labels)}")
                    if source_labels
                    else ("没有可展示的行情来源。" if zh else "No displayable price source."),
                ],
                risk_level="medium",
            )
        )

    limitations = [str(item) for item in research.get("limitations") or []]
    if benchmark.get("limitation"):
        limitations.append(str(benchmark["limitation"]))
    limitations.extend(str(item) for item in readiness.get("limitations") or [])
    limitations.append(READ_ONLY_LIMITATION)
    readiness_status = str(readiness.get("status") or "")
    if readiness_status == "insufficient_data":
        next_step = (
            "先补全收入与支出基线，再讨论假设投资场景。"
            if zh
            else "Complete the income and expense baseline before discussing a hypothetical investment scenario."
        )
    elif readiness_status == "caution":
        next_step = (
            "先稳定现金流与流动储备，再比较假设场景。"
            if zh
            else "Stabilize cash flow and liquid reserves before comparing hypothetical scenarios."
        )
    else:
        next_step = (
            "在假设场景中比较仓位集中度，并检查来源时间。"
            if zh
            else "Compare concentration in a hypothetical scenario and verify source timestamps."
        )
    return SpecialistAgentOutput(
        specialist="investment_research",
        confidence=0.82 if quote and change is not None else 0.62,
        findings=findings,
        recommendations=[
            SpecialistRecommendation(
                title="先核对证据与风险边界" if zh else "Review evidence and risk boundaries first",
                rationale=(
                    "历史价格和单一行情快照不能证明未来收益。"
                    if zh
                    else "Historical prices and a single quote do not establish future returns."
                ),
                next_step=next_step,
            )
        ],
        limitations=list(dict.fromkeys(limitations)),
    )
