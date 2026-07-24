"""Build the deterministic, typed CFO response from approved evidence."""

from __future__ import annotations

from typing import Any

from app.agents.specialists.contracts import SpecialistAgentOutput
from app.models.agent_data import AgentAction, AgentAudit, AgentFinding, SummaryCard
from app.models.runtime import RuntimePolicyResult
from app.runtime.response.response_composer import compose_finance_chat_response


def _round_money(value: float | int | None) -> float:
    return round(float(value or 0), 2)


def _status_from_budget(status: str) -> str:
    if status == "good":
        return "good"
    if status == "risk":
        return "risk"
    if status == "watch":
        return "watch"
    return "neutral"


BUDGET_STATUS_ZH = {
    "good": "良好",
    "watch": "观察",
    "risk": "风险",
    "data_limited": "数据不足",
}


def _summary_cards(context: dict[str, Any]) -> list[SummaryCard]:
    expense = context.get("expense_snapshot", {})
    budget = context.get("budget_snapshot", {})
    zh = context.get("reply_language") == "zh"
    budget_status = str(budget.get("status") or "data_limited")
    return [
        SummaryCard(
            label="净现金流" if zh else "Net cash flow",
            value=f"{_round_money(expense.get('net_total')):,.2f}",
            status="good"
            if float(expense.get("net_total") or 0) >= 0
            else "watch",
            note=(
                "已加载交易的收入减支出"
                if zh
                else "Income minus expenses from loaded transactions"
            ),
        ),
        SummaryCard(
            label="支出" if zh else "Expenses",
            value=f"{_round_money(expense.get('expense_total')):,.2f}",
            status="neutral",
            note=(
                f"{int(expense.get('transaction_count') or 0)} 笔有效交易"
                if zh
                else (
                    f"{int(expense.get('transaction_count') or 0)} "
                    "active transactions"
                )
            ),
        ),
        SummaryCard(
            label="预算状态" if zh else "Budget status",
            value=(
                BUDGET_STATUS_ZH.get(budget_status, budget_status)
                if zh
                else budget_status
            ),
            status=_status_from_budget(budget_status),
            note=(
                "支出与设定月收入之比"
                if zh
                else "Expense ratio against configured monthly income"
            ),
        ),
    ]


def _response_summary_cards(context: dict[str, Any]) -> list[SummaryCard]:
    query = context.get("transaction_query")
    if query is not None:
        zh = context.get("reply_language") == "zh"
        share = query.get("share_of_scope")
        return [
            SummaryCard(
                label="匹配金额" if zh else "Matched amount",
                value=f"{_round_money(query.get('total')):,.2f}",
                status="neutral",
                note="类型化账本查询" if zh else "Typed ledger query",
            ),
            SummaryCard(
                label="交易笔数" if zh else "Transactions",
                value=str(int(query.get("count") or 0)),
                status="neutral",
                note="符合当前筛选条件" if zh else "Matching current filters",
            ),
            SummaryCard(
                label="同期占比" if zh else "Share of scope",
                value=(
                    f"{float(share) * 100:.1f}%"
                    if share is not None
                    else "—"
                ),
                status="good" if share is not None else "neutral",
                note=(
                    "占同期同方向总额"
                    if zh
                    else "Of the scoped direction total"
                ),
            ),
        ]

    research = context.get("investment_research") or {}
    status = research.get("status")
    if status in {"symbol_required", "unavailable"}:
        return []
    if status != "available":
        return _summary_cards(context)

    zh = context.get("reply_language") == "zh"
    quote = research.get("quote") or {}
    price = quote.get("price") or {}
    history = research.get("history") or {}
    evidence = research.get("evidence") or []
    quote_value = price.get("amount")
    quote_currency = str(price.get("currency") or "")
    change = history.get("change_percent")
    return [
        SummaryCard(
            label="最近行情" if zh else "Latest quote",
            value=(
                f"{quote_currency} {quote_value}"
                if quote_value is not None
                else ("暂无" if zh else "Unavailable")
            ),
            status="neutral",
            note=(
                f"来源 {quote.get('source')}; 截至 {quote.get('quote_as_of')}"
                if zh
                else (
                    f"Source {quote.get('source')}; "
                    f"as of {quote.get('quote_as_of')}"
                )
            ),
        ),
        SummaryCard(
            label="观察期变化" if zh else "Observed change",
            value=(
                f"{change}%"
                if change is not None
                else ("暂无" if zh else "Unavailable")
            ),
            status="watch" if change is not None else "neutral",
            note=(
                f"{history.get('date_from')} 至 {history.get('date_to')}"
                if zh
                else f"{history.get('date_from')} to {history.get('date_to')}"
            ),
        ),
        SummaryCard(
            label="证据来源" if zh else "Evidence sources",
            value=str(len(evidence)),
            status="good" if evidence else "watch",
            note=(
                "只读研究，不执行交易"
                if zh
                else "Read-only research; no trade execution"
            ),
        ),
    ]


class FinanceResponseBuilder:
    """Project approved runtime artifacts into the public chat contract."""

    @staticmethod
    def resolve_language(preferences: dict[str, Any], message: str) -> str:
        preferred = str(preferences.get("preferred_language") or "auto")
        if preferred in ("zh", "en"):
            return preferred
        return "zh" if any("一" <= ch <= "鿿" for ch in message) else "en"

    def build(
        self,
        *,
        context: dict[str, Any],
        policy: RuntimePolicyResult,
        specialist_outputs: dict[str, SpecialistAgentOutput],
    ) -> dict[str, Any]:
        expense = context.get("expense_snapshot", {})
        budget = context.get("budget_snapshot", {})
        findings: list[AgentFinding] = []
        actions: list[AgentAction] = []
        warnings: list[str] = []
        knowledge = context.get("knowledge_retrieval") or {}

        for item in (knowledge.get("artifacts") or [])[:2]:
            freshness = item.get("freshness") or "current"
            findings.append(
                AgentFinding(
                    agent="cfo",
                    title=str(item.get("title") or "Reviewed finance guidance"),
                    evidence=[
                        f"{item.get('source_authority')} · "
                        f"{item.get('section')} · {freshness}"
                    ],
                )
            )

        for specialist, output in specialist_outputs.items():
            if specialist == "auditor":
                warnings.extend(output.limitations)
                warnings.extend(
                    evidence
                    for finding in output.findings
                    for evidence in finding.evidence
                    if finding.risk_level != "low"
                )
                continue
            findings.extend(
                AgentFinding(
                    agent=specialist,
                    title=finding.title,
                    evidence=finding.evidence,
                )
                for finding in output.findings
            )
            actions.extend(
                AgentAction(
                    title=recommendation.title,
                    rationale=recommendation.rationale,
                    effort="medium",
                    impact="high" if policy.risk_level == "high" else "medium",
                )
                for recommendation in output.recommendations
            )

        if not findings and expense.get("transaction_count"):
            findings.append(
                AgentFinding(
                    agent="cfo",
                    title="Loaded transaction context is available",
                    evidence=[
                        f"{expense.get('transaction_count')} transactions; "
                        f"net cash flow {expense.get('net_total')}."
                    ],
                )
            )

        audit_output = specialist_outputs.get("auditor")
        audit_status = (
            "needs_review" if policy.audit_required or warnings else "verified"
        )
        has_scoped_query_evidence = context.get("transaction_query") is not None
        has_investment_evidence = (
            (context.get("investment_research") or {}).get("status")
            == "available"
        )
        if (
            not context.get("transactions_sample")
            and not has_scoped_query_evidence
            and not has_investment_evidence
        ):
            audit_status = "data_limited"
        audit = AgentAudit(
            confidence=audit_output.confidence if audit_output else 0.68,
            status=audit_status,
            warnings=warnings[:5],
        )

        query = context.get("transaction_query")
        preferences = (context.get("profile") or {}).get("preferences") or {}
        language = self.resolve_language(
            preferences,
            context.get("message") or "",
        )
        tone = str(preferences.get("response_tone") or "balanced")
        evidence_level = str(
            preferences.get("evidence_level") or "detailed"
        )

        budget_status = budget.get("status") or "data_limited"
        budget_status_zh = BUDGET_STATUS_ZH.get(
            budget_status,
            budget_status,
        )
        net_total = _round_money(expense.get("net_total"))
        expense_total = _round_money(expense.get("expense_total"))

        query_line = ""
        if query:
            query_filters = query.get("filters") or {}
            scope_parts = []
            if query_filters.get("date_from"):
                scope_parts.append(
                    f"{query_filters['date_from']} ~ "
                    f"{query_filters.get('date_to', '')}"
                )
            if query_filters.get("category"):
                category_zh = {
                    "dining": "餐饮",
                    "transport": "交通",
                    "shopping": "购物",
                    "groceries": "买菜",
                    "housing": "住房",
                    "entertainment": "娱乐",
                    "travel": "旅行",
                    "utilities": "水电",
                    "services": "订阅服务",
                    "health": "医疗",
                    "transfer": "转账",
                    "education": "教育",
                }
                label = str(query_filters["category"])
                scope_parts.append(
                    category_zh.get(label, label)
                    if language == "zh"
                    else label
                )
            scope = " ".join(scope_parts)
            if language == "zh":
                kind = (
                    "收入"
                    if query_filters.get("direction") == "income"
                    else "支出"
                )
                query_line = (
                    f"{scope}{kind}合计 {query['total']:,.2f}"
                    f"（{query['count']} 笔）。"
                )
                if query.get("share_of_scope") is not None:
                    query_line += (
                        f"占同期总{kind}的 "
                        f"{float(query['share_of_scope']) * 100:.1f}%。"
                    )
            else:
                kind = (
                    "income"
                    if query_filters.get("direction") == "income"
                    else "spend"
                )
                query_line = (
                    f"{scope} {kind} totals {query['total']:,.2f} "
                    f"across {query['count']} transactions. "
                )
                if query.get("share_of_scope") is not None:
                    query_line += (
                        f"It represents "
                        f"{float(query['share_of_scope']) * 100:.1f}% "
                        f"of scoped {kind}. "
                    )

        investment = context.get("investment_research") or {}
        if investment.get("status") == "available":
            symbol = str(investment.get("symbol") or "")
            quote = investment.get("quote") or {}
            quote_price = quote.get("price") or {}
            price = quote_price.get("amount")
            currency = quote_price.get("currency") or ""
            if language == "zh":
                reply = f"我已按只读研究流程核对 {symbol} 的有来源行情证据。"
                if price is not None:
                    reply += f"最近行情为 {currency} {price}。"
                reply += "历史行情不代表未来收益，也不会触发任何交易。"
            else:
                reply = (
                    f"I reviewed sourced {symbol} market evidence "
                    "in read-only mode. "
                )
                if price is not None:
                    reply += f"The latest quote is {currency} {price}. "
                reply += (
                    "Historical prices do not predict future returns, "
                    "and no trade is executed."
                )
            if actions:
                reply += (
                    f"下一步：{actions[0].title}。"
                    if language == "zh"
                    else f" Next: {actions[0].title}."
                )
        elif investment.get("status") in {
            "symbol_required",
            "unavailable",
        }:
            reply = (
                "我还不能完成这次投资研究：请提供明确的股票或 ETF 代码，"
                "并确认行情数据源可用。"
                if language == "zh"
                else (
                    "I cannot complete this investment research yet: "
                    "provide an explicit stock or ETF symbol and ensure "
                    "the market-data source is available."
                )
            )
        elif knowledge.get("match_status") == "matched":
            first = (knowledge.get("artifacts") or [])[0]
            excerpt = str(first.get("excerpt") or "").strip()[:600]
            authority = str(
                first.get("source_authority") or "reviewed source"
            )
            stale_note = (
                "该资料已超过复核日期，请先核对最新规则。"
                if first.get("freshness") == "stale" and language == "zh"
                else (
                    " This source is past its review date; "
                    "verify the latest rule."
                )
                if first.get("freshness") == "stale"
                else ""
            )
            reply = (
                f"根据已审核的 {authority} 指引：{excerpt}{stale_note}"
                if language == "zh"
                else (
                    f"Based on reviewed guidance from {authority}: "
                    f"{excerpt}{stale_note}"
                )
            )
        elif query_line:
            reply = query_line
            if actions and language == "zh":
                reply += f"另外，最高优先级建议：{actions[0].title}。"
            elif actions:
                reply += f"Also worth noting: {actions[0].title}."
        elif language == "zh":
            reply = (
                "我以 CFO 优先流程复核了你已加载的财务数据。"
                f"当前净现金流 {net_total:,.2f}，"
                f"支出合计 {expense_total:,.2f}，"
                f"预算状态为{budget_status_zh}。"
            )
            if actions:
                reply += f"最高优先级：{actions[0].title}。"
            elif not context.get("transactions_sample"):
                reply += "建议先导入交易或账单数据，再依赖详细建议。"
            else:
                reply += "请持续关注最大的支出类目，并在新交易后刷新数据。"
        else:
            reply = (
                "I reviewed your loaded finance context with a CFO-first flow. "
                f"Current net cash flow is {net_total:,.2f}, "
                f"expense total is {expense_total:,.2f}, "
                f"and budget status is {budget_status}. "
            )
            if actions:
                reply += f"Highest priority: {actions[0].title}."
            elif not context.get("transactions_sample"):
                reply += (
                    "Add transactions or statement data before relying "
                    "on detailed recommendations."
                )
            else:
                reply += (
                    "Keep monitoring the largest categories and refresh "
                    "the data after new transactions."
                )

        if knowledge.get("match_status") == "no_match":
            no_match_note = (
                "现有已审核知识库没有直接匹配这个问题；"
                "以上结论未使用外部政策资料。"
                if language == "zh"
                else (
                    "The reviewed knowledge base has no direct match for "
                    "this question; no external policy guidance was used above."
                )
            )
            reply = (
                f"{no_match_note}{reply}"
                if language == "zh"
                else f"{no_match_note} {reply}"
            )

        if tone == "concise":
            reply = (
                reply.split("。")[0] + "。"
                if language == "zh"
                else reply.split(". ")[0] + "."
            )
            if actions:
                top = (
                    f"最高优先级：{actions[0].title}。"
                    if language == "zh"
                    else f" Top action: {actions[0].title}."
                )
                reply += top
        elif tone == "comprehensive":
            extra = (
                f"共 {len(findings)} 条发现、{len(actions)} 条建议；"
                f"审计状态 {audit.status}。"
                if language == "zh"
                else (
                    f" In total: {len(findings)} findings and "
                    f"{len(actions)} actions; audit status {audit.status}."
                )
            )
            reply += extra

        if evidence_level == "brief":
            findings = [
                finding.model_copy(update={"evidence": finding.evidence[:1]})
                for finding in findings
            ]
            audit = audit.model_copy(update={"warnings": audit.warnings[:2]})
        elif evidence_level == "audit_heavy":
            audit_note = (
                f"审计置信度 {audit.confidence:.2f}，"
                f"警告 {len(audit.warnings)} 条。"
                if language == "zh"
                else (
                    f" Audit confidence {audit.confidence:.2f} "
                    f"with {len(audit.warnings)} warnings."
                )
            )
            reply += audit_note

        return compose_finance_chat_response(
            reply=reply,
            summary_cards=_response_summary_cards(context),
            findings=findings,
            actions=actions,
            audit=audit,
        )
