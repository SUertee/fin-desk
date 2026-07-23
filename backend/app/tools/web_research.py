"""Agent-facing tool boundary for governed external web research."""

from __future__ import annotations

import re
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.connectors.web_search.errors import WebSearchBudgetExceeded
from app.models.web_research import WebResearchRequest
from app.runtime.execution import AgentContext, ToolObservation, ToolSpec
from app.services.web_research import WebResearchBudget, WebResearchService


_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_LONG_IDENTIFIER_RE = re.compile(r"(?<!\d)\d{8,}(?!\d)")
_MAX_QUERY_LENGTH = 240
_PROFILE_KEYS = ("name", "email", "phone")


class WebResearchToolInput(BaseModel):
    """Minimal model-controlled input; governance stays system-owned."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=500)
    topic: Literal["general", "news"] = "news"


def sanitize_web_research_query(
    query: str,
    *,
    profile: dict[str, Any] | None = None,
) -> str:
    """Remove obvious identifiers before a query leaves FinDesk."""

    sanitized = " ".join(query.split())
    for key in _PROFILE_KEYS:
        value = str((profile or {}).get(key) or "").strip()
        if len(value) >= 2:
            sanitized = re.sub(
                re.escape(value),
                "[redacted-profile]",
                sanitized,
                flags=re.IGNORECASE,
            )
    sanitized = _EMAIL_RE.sub("[redacted-email]", sanitized)
    sanitized = _LONG_IDENTIFIER_RE.sub("[redacted-number]", sanitized)
    return sanitized[:_MAX_QUERY_LENGTH].rstrip()


class WebResearchTool:
    """Translate runtime context into a bounded web-research observation."""

    name = "search_web_research"

    def __init__(self, service: WebResearchService):
        self.service = service

    def new_budget(self) -> WebResearchBudget:
        return self.service.new_budget()

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description="Search allowlisted external sources for current market context.",
            executor=self.execute,
            owner="market_context",
            deterministic=False,
        )

    async def execute(self, payload: dict[str, Any]) -> ToolObservation:
        started = perf_counter()
        agent = str(payload.get("agent") or "cfo")
        context = payload.get("context")
        budget = payload.get("web_research_budget")
        if not isinstance(context, AgentContext):
            return self._failure(
                agent=agent,
                started=started,
                error_class="invalid_tool_input",
                error_message="AgentContext is required",
            )
        if not isinstance(budget, WebResearchBudget):
            return self._failure(
                agent=agent,
                started=started,
                error_class="missing_run_budget",
                error_message="A run-scoped web research budget is required",
            )

        query = sanitize_web_research_query(
            context.effective_message,
            profile=context.profile,
        )
        try:
            tool_input = WebResearchToolInput(query=query, topic="news")
            result = self.service.search(
                WebResearchRequest(
                    query=tool_input.query,
                    topic=tool_input.topic,
                    max_results=self.service.settings.max_results,
                ),
                budget=budget,
            )
        except WebSearchBudgetExceeded as exc:
            return self._failure(
                agent=agent,
                started=started,
                error_class="external_call_budget_exceeded",
                error_message=str(exc),
            )
        except ValueError as exc:
            return self._failure(
                agent=agent,
                started=started,
                error_class="invalid_web_research_request",
                error_message=str(exc),
            )

        return ToolObservation(
            tool_name=self.name,
            success=True,
            agent=agent,
            purpose="governed_external_research",
            result=result.model_dump(mode="json"),
            latency_ms=round((perf_counter() - started) * 1000, 2),
            evidence_refs=[item.url for item in result.items],
        )

    def _failure(
        self,
        *,
        agent: str,
        started: float,
        error_class: str,
        error_message: str,
    ) -> ToolObservation:
        return ToolObservation(
            tool_name=self.name,
            success=False,
            agent=agent,
            purpose="governed_external_research",
            error_class=error_class,
            error_message=error_message,
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )
