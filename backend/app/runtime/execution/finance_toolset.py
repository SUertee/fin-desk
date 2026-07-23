"""Deterministic finance tools exposed to the CFO runtime."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from time import perf_counter
from typing import Any

from app.connectors.postgres.statement_import_store import (
    list_latest_quality_reports_db,
)
from app.knowledge import KnowledgeQuery, KnowledgeRetriever
from app.runtime.execution.context import AgentContext
from app.runtime.execution.tool_executor import (
    ToolObservation,
    ToolRegistry,
    ToolSpec,
)
from app.services.investment_research_runtime import (
    get_investment_research_service,
)
from app.tools.finance_tools import (
    build_budget_snapshot,
    build_expense_snapshot,
    build_finance_context_payload,
)
from app.tools.investment_research_tools import (
    extract_instrument_reference,
    project_instrument_research,
)
from app.tools.mcp_market_data import VibeMarketDataTool
from app.tools.query_tools import extract_query_filters, run_transaction_query
from app.tools.web_research import WebResearchTool

logger = logging.getLogger(__name__)


class FinanceToolset:
    """Own the runtime's deterministic tool implementations and registry."""

    def __init__(
        self,
        *,
        knowledge_retriever: KnowledgeRetriever,
        web_research_tool: WebResearchTool,
        mcp_market_data_tool: VibeMarketDataTool | None = None,
    ) -> None:
        self.knowledge_retriever = knowledge_retriever
        self.web_research_tool = web_research_tool
        self.mcp_market_data_tool = mcp_market_data_tool

    def build_registry(self) -> ToolRegistry:
        specs = [
            ToolSpec(
                name="get_finance_context",
                description="Build a complete finance context payload.",
                executor=self.finance_context,
            ),
            ToolSpec(
                name="get_expense_snapshot",
                description="Summarize transactions, categories, and anomalies.",
                executor=self.expense_snapshot,
            ),
            ToolSpec(
                name="get_budget_snapshot",
                description="Summarize income, expense ratio, and budget status.",
                executor=self.budget_snapshot,
            ),
            ToolSpec(
                name="get_anomaly_summary",
                description="Return anomaly summary from the expense snapshot.",
                executor=self.anomaly_summary,
            ),
            ToolSpec(
                name="get_cashflow_summary",
                description="Summarize monthly cash flow totals.",
                executor=self.cashflow_summary,
            ),
            ToolSpec(
                name="get_import_quality_report",
                description="Latest statement-import quality report per source.",
                executor=self.import_quality,
            ),
            ToolSpec(
                name="query_transactions",
                description="Typed ledger aggregation from extracted filters (nl2filters).",
                executor=self.query_transactions,
            ),
            ToolSpec(
                name="search_knowledge",
                description="Search reviewed finance guidance with bounded lexical retrieval.",
                executor=self.search_knowledge,
                owner="knowledge",
            ),
            ToolSpec(
                name="get_investment_research_context",
                description="Fetch bounded, sourced stock or ETF research evidence.",
                executor=self.investment_research_context,
                owner="investment_research",
            ),
            self.web_research_tool.spec(),
        ]
        if self.mcp_market_data_tool is not None:
            specs.append(self.mcp_market_data_tool.spec())
        return ToolRegistry(specs)

    async def search_knowledge(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        try:
            result = self.knowledge_retriever.retrieve(
                KnowledgeQuery(text=context.effective_message, top_k=4)
            )
        except Exception as exc:
            logger.warning(
                "Knowledge retrieval unavailable: %s",
                type(exc).__name__,
            )
            return ToolObservation(
                tool_name="search_knowledge",
                success=False,
                agent=str(payload.get("agent") or "cfo"),
                purpose="reviewed_knowledge_evidence",
                error_class=type(exc).__name__,
                error_message="Reviewed knowledge is currently unavailable.",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        return ToolObservation(
            tool_name="search_knowledge",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="reviewed_knowledge_evidence",
            result=result.model_dump(mode="json"),
            evidence_refs=[item.citation_id for item in result.artifacts],
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    @staticmethod
    def knowledge_ledger_projection(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item.get(key)
            for key in (
                "citation_id",
                "document_id",
                "chunk_id",
                "title",
                "section",
                "excerpt",
                "source_url",
                "source_authority",
                "jurisdiction",
                "reviewed_at",
                "review_after",
                "freshness",
                "retrieval_method",
            )
        }

    async def investment_research_context(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        reference = extract_instrument_reference(context.effective_message)
        if reference is None:
            return ToolObservation(
                tool_name="get_investment_research_context",
                success=True,
                agent=str(payload.get("agent") or "cfo"),
                purpose="sourced_investment_research",
                result={
                    "status": "symbol_required",
                    "reason": (
                        "An explicit stock or ETF symbol is required; "
                        "company names are not inferred."
                    ),
                    "trade_actions_allowed": False,
                },
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

        symbol, asset_type = reference
        date_to = date.today()
        try:
            snapshot = (
                get_investment_research_service().get_instrument_research(
                    context.user_id,
                    symbol,
                    asset_type=asset_type,
                    date_from=date_to - timedelta(days=90),
                    date_to=date_to,
                )
            )
            result = project_instrument_research(snapshot)
        except Exception as exc:
            logger.warning(
                "Investment research unavailable symbol=%s error=%s",
                symbol,
                type(exc).__name__,
            )
            result = {
                "status": "unavailable",
                "symbol": symbol,
                "asset_type": asset_type,
                "reason": "Sourced market evidence is currently unavailable.",
                "trade_actions_allowed": False,
            }
        return ToolObservation(
            tool_name="get_investment_research_context",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="sourced_investment_research",
            result=result,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def query_transactions(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        filters = extract_query_filters(context.effective_message)
        result = run_transaction_query(context.user_id, filters)
        return ToolObservation(
            tool_name="query_transactions",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="typed_ledger_query",
            result=result,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def import_quality(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        reports = list_latest_quality_reports_db(context.user_id)
        return ToolObservation(
            tool_name="get_import_quality_report",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="data_quality_evidence",
            result={"reports": reports},
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    @staticmethod
    def context_payload(context: AgentContext) -> dict[str, Any]:
        return build_finance_context_payload(
            user_id=context.user_id,
            profile=context.profile,
            transactions=context.transactions,
            monthly_totals=context.monthly_totals,
            chat_history=context.chat_history,
            memory_context=context.memory_context,
        ) | {
            "message": context.effective_message,
            "runtime_policy": context.runtime_policy,
        }

    async def finance_context(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        return ToolObservation(
            tool_name="get_finance_context",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="baseline_context",
            result=self.context_payload(context),
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def expense_snapshot(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        return ToolObservation(
            tool_name="get_expense_snapshot",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="expense_evidence",
            result=build_expense_snapshot(
                context.transactions,
                context.monthly_totals,
            ),
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def budget_snapshot(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        return ToolObservation(
            tool_name="get_budget_snapshot",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="budget_evidence",
            result=build_budget_snapshot(
                context.profile,
                context.transactions,
                context.monthly_totals,
            ),
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def anomaly_summary(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        snapshot = (payload.get("artifacts") or {}).get(
            "get_expense_snapshot"
        ) or {}
        return ToolObservation(
            tool_name="get_anomaly_summary",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="anomaly_evidence",
            result={
                "anomaly_count": snapshot.get("anomaly_count", 0),
                "anomalies": snapshot.get("anomalies", []),
            },
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def cashflow_summary(
        self, payload: dict[str, Any]
    ) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        net_total = sum(
            float(item.get("net") or 0) for item in context.monthly_totals
        )
        return ToolObservation(
            tool_name="get_cashflow_summary",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="cashflow_evidence",
            result={
                "month_count": len(context.monthly_totals),
                "net_total": round(net_total, 2),
                "monthly_totals": context.monthly_totals,
            },
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )
