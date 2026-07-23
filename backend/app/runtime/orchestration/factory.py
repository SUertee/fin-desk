"""Concrete composition root for the finance runtime."""

from __future__ import annotations

from typing import Any

from app.agents.cfo import CfoDecisionEngine
from app.connectors.postgres.exchange_rate_store import (
    get_exchange_rate_snapshot_db,
)
from app.knowledge import KnowledgeRetriever
from app.knowledge.factory import build_knowledge_retriever
from app.runtime.capabilities import (
    CapabilityCatalog,
    CapabilityHealthService,
    CapabilityResolver,
    get_capability_health_service,
)
from app.runtime.capabilities.contracts import CapabilityRuntimeStatus
from app.runtime.costing import CostingService
from app.runtime.execution import ToolRegistry
from app.runtime.execution.finance_toolset import FinanceToolset
from app.runtime.execution.finance_turn_executor import FinanceTurnExecutor
from app.runtime.execution.specialist_runner import SpecialistRunner
from app.runtime.llm.deepseek_client import DeepSeekTextClient
from app.runtime.orchestration.finance_runtime import FinanceRuntime
from app.runtime.orchestration.intake import (
    ModelTurnContextualizer,
    TurnContextualizer,
)
from app.runtime.response.cfo_reply_generator import CfoReplyGenerator
from app.runtime.response.finance_response_builder import FinanceResponseBuilder
from app.services.web_research import (
    WebResearchService,
    build_web_research_service,
)
from app.tools.mcp_market_data import (
    VibeMarketDataTool,
    build_vibe_market_data_tool,
)
from app.tools.web_research import WebResearchTool
from app.config.settings import get_settings

_DEFAULT = object()


def build_finance_runtime(
    *,
    tool_registry: ToolRegistry | None = None,
    specialist_runner: SpecialistRunner | None = None,
    llm_client: Any = _DEFAULT,
    costing_service: CostingService | None = None,
    web_research_service: WebResearchService | None = None,
    web_research_tool: WebResearchTool | None = None,
    mcp_market_data_tool: VibeMarketDataTool | None = None,
    capability_health_service: CapabilityHealthService | None = None,
    granted_capabilities: set[str] | None = None,
    knowledge_retriever: KnowledgeRetriever | None = None,
    decision_engine: CfoDecisionEngine | None = None,
    response_builder: FinanceResponseBuilder | None = None,
    reply_generator: CfoReplyGenerator | None = None,
    toolset: FinanceToolset | None = None,
    turn_executor: FinanceTurnExecutor | None = None,
    turn_contextualizer: TurnContextualizer | None = None,
) -> FinanceRuntime:
    """Build one runtime without performing network work during import."""

    research_tool = web_research_tool or WebResearchTool(
        web_research_service or build_web_research_service()
    )
    mcp_settings = get_settings().mcp
    injected_mcp_tool = mcp_market_data_tool is not None
    market_data_tool = mcp_market_data_tool
    if market_data_tool is None and mcp_settings.enabled:
        market_data_tool = build_vibe_market_data_tool(mcp_settings)

    health_service = capability_health_service
    if (
        health_service is None
        and market_data_tool is not None
        and not injected_mcp_tool
    ):
        health_service = get_capability_health_service()

    retriever = knowledge_retriever or build_knowledge_retriever()
    finance_toolset = toolset or FinanceToolset(
        knowledge_retriever=retriever,
        web_research_tool=research_tool,
        mcp_market_data_tool=market_data_tool,
    )
    registry = tool_registry or finance_toolset.build_registry()
    runner = specialist_runner or SpecialistRunner()

    optional_statuses = None
    if market_data_tool is None and not injected_mcp_tool:
        optional_statuses = {
            "get_vibe_market_data": CapabilityRuntimeStatus(
                enabled=False,
                available=False,
                reason="Disabled by configuration",
            )
        }
    catalog = CapabilityCatalog.from_registries(
        registry,
        runner.registry,
        optional_tool_statuses=optional_statuses,
    )
    resolver = CapabilityResolver(catalog)
    available_capabilities = frozenset(
        item.descriptor.capability_id
        for item in catalog.list()
        if item.status.enabled and item.status.available
    )
    grants = frozenset(
        granted_capabilities
        if granted_capabilities is not None
        else available_capabilities
    )

    client = DeepSeekTextClient() if llm_client is _DEFAULT else llm_client
    builder = response_builder or FinanceResponseBuilder()
    contextualizer = turn_contextualizer or TurnContextualizer(
        model=ModelTurnContextualizer(lambda: client)
    )
    cfo_decision = decision_engine or CfoDecisionEngine(lambda: client)
    generator = reply_generator or CfoReplyGenerator(
        lambda: client,
        builder.resolve_language,
    )
    executor = turn_executor or FinanceTurnExecutor(
        capability_catalog=catalog,
        capability_resolver=resolver,
        granted_capabilities=grants,
        tool_registry=registry,
        toolset=finance_toolset,
        specialist_runner=runner,
        web_research_tool=research_tool,
        capability_health_service=health_service,
    )
    costing = costing_service or CostingService(
        exchange_rate_lookup=get_exchange_rate_snapshot_db
    )

    return FinanceRuntime(
        tool_registry=registry,
        capability_catalog=catalog,
        granted_capabilities=grants,
        turn_contextualizer=contextualizer,
        decision_engine=cfo_decision,
        turn_executor=executor,
        response_builder=builder,
        reply_generator=generator,
        costing_service=costing,
    )
