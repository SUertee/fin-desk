"""FinDesk adapter for the allowlisted Vibe-Trading MCP market-data tool."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from time import perf_counter
from typing import Any, Callable

from app.config.settings import McpSettings
from app.connectors.mcp import (
    McpClientError,
    McpResponseContractError,
    McpToolClient,
    McpToolResponse,
    build_mcp_client,
)
from app.models.external_market_data import ExternalMarketHistoryArtifact
from app.runtime.execution.context import AgentContext
from app.runtime.execution.tool_executor import ToolObservation, ToolSpec
from app.tools.investment_research_tools import extract_instrument_reference


EXTERNAL_MARKET_HISTORY_CAPABILITY = "investment.external_market_history"
_EXTERNAL_MARKET_TERMS = (
    "mcp",
    "vibe",
    "外部行情",
    "外部市场数据",
    "外部数据源",
)


def has_external_market_data_intent(message: str) -> bool:
    text = str(message or "").lower()
    return any(term in text for term in _EXTERNAL_MARKET_TERMS)


def _provider_symbol(symbol: str) -> str:
    if any(marker in symbol for marker in (".", "-", "/")):
        return symbol
    return f"{symbol}.US"


def _currency_for_symbol(symbol: str) -> str | None:
    if symbol.endswith(".US"):
        return "USD"
    if symbol.endswith(".HK"):
        return "HKD"
    if symbol.endswith((".SZ", ".SH")):
        return "CNY"
    if symbol.endswith("-USDT") or symbol.endswith("/USDT"):
        return "USDT"
    return None


def _response_payload(response: McpToolResponse) -> dict[str, Any]:
    candidate: Any = response.structured_content
    if isinstance(candidate, dict) and "result" in candidate:
        candidate = candidate["result"]
    if candidate is None:
        candidate = response.text
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise McpResponseContractError("MCP market data is not valid JSON") from exc
    if not isinstance(candidate, dict):
        raise McpResponseContractError("MCP market data must be a JSON object")
    return candidate


def _row_value(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _period_return(first_close: Decimal | None, last_close: Decimal | None) -> Decimal | None:
    if first_close is None or last_close is None or first_close == 0:
        return None
    return ((last_close / first_close) - Decimal("1")) * Decimal("100")


def normalize_market_history(
    response: McpToolResponse,
    *,
    symbol: str,
    provider_symbol: str,
    asset_type: str,
    date_from: date,
    date_to: date,
    source_requested: str,
    max_rows: int,
    fetched_at: datetime,
) -> ExternalMarketHistoryArtifact:
    payload = _response_payload(response)
    raw = payload.get(provider_symbol, payload.get(symbol))
    unresolved = payload.get("_unresolved") or []
    if raw is None or provider_symbol in unresolved or symbol in unresolved:
        return ExternalMarketHistoryArtifact(
            status="unavailable",
            symbol=symbol,
            provider_symbol=provider_symbol,
            asset_type=asset_type,
            date_from=date_from,
            date_to=date_to,
            source_requested=source_requested,
            fetched_at=fetched_at,
            reason="The MCP market-data provider could not resolve the symbol.",
            limitations=(
                "No alternative provider was used for this explicit MCP request.",
            ),
        )

    truncated = False
    if isinstance(raw, dict):
        truncated = bool(raw.get("truncated"))
        raw = raw.get("data")
    if not isinstance(raw, list) or not all(isinstance(row, dict) for row in raw):
        raise McpResponseContractError("MCP market history has an invalid row shape")
    if len(raw) > max_rows:
        raise McpResponseContractError("MCP market history exceeds the row limit")
    if not raw:
        return ExternalMarketHistoryArtifact(
            status="unavailable",
            symbol=symbol,
            provider_symbol=provider_symbol,
            asset_type=asset_type,
            date_from=date_from,
            date_to=date_to,
            source_requested=source_requested,
            fetched_at=fetched_at,
            reason="The MCP market-data provider returned no price bars.",
        )

    first_close = _decimal(_row_value(raw[0], "close"))
    last_close = _decimal(_row_value(raw[-1], "close"))
    latest_as_of = _row_value(
        raw[-1], "trade_date", "date", "datetime", "index"
    )
    limitations = (
        "The MCP response does not identify the effective upstream loader after provider fallback.",
        "Currency is inferred from the explicit symbol suffix when available.",
        "Historical market data is read-only evidence and does not authorize trading.",
    )
    period_return = _period_return(first_close, last_close)
    return ExternalMarketHistoryArtifact(
        status="available",
        symbol=symbol,
        provider_symbol=provider_symbol,
        asset_type=asset_type,
        date_from=date_from,
        date_to=date_to,
        source_requested=source_requested,
        bar_count=len(raw),
        first_close=first_close,
        last_close=last_close,
        latest_as_of=str(latest_as_of)[:40] if latest_as_of is not None else None,
        period_return_percent=(
            period_return.quantize(Decimal("0.01"))
            if period_return is not None
            else None
        ),
        currency=_currency_for_symbol(provider_symbol),
        truncated=truncated,
        fetched_at=fetched_at,
        evidence_refs=(
            f"mcp:vibe_trading:get_market_data:{provider_symbol}:{date_from}:{date_to}",
        ),
        limitations=limitations,
    )


def project_external_history_for_specialist(
    artifact: ExternalMarketHistoryArtifact,
) -> dict[str, Any]:
    base = {
        "status": artifact.status,
        "symbol": artifact.symbol,
        "asset_type": artifact.asset_type,
        "reason": artifact.reason,
        "limitations": list(artifact.limitations),
        "trade_actions_allowed": False,
    }
    if artifact.status != "available":
        return base
    quote = None
    if artifact.last_close is not None and artifact.currency:
        quote = {
            "price": {
                "amount": str(artifact.last_close),
                "currency": artifact.currency,
            },
            "quote_as_of": artifact.latest_as_of,
            "source": artifact.provider,
        }
    return {
        **base,
        "profile": {
            "name": artifact.provider_symbol,
            "currency": artifact.currency,
            "source": artifact.provider,
            "fetched_at": artifact.fetched_at.isoformat(),
        },
        "quote": quote,
        "history": {
            "date_from": artifact.date_from.isoformat(),
            "date_to": artifact.date_to.isoformat(),
            "bar_count": artifact.bar_count,
            "first_close": str(artifact.first_close) if artifact.first_close is not None else None,
            "last_close": str(artifact.last_close) if artifact.last_close is not None else None,
            "change_percent": (
                str(artifact.period_return_percent)
                if artifact.period_return_percent is not None
                else None
            ),
            "currency": artifact.currency,
            "source": artifact.provider,
            "fetched_at": artifact.fetched_at.isoformat(),
        },
        "performance": {
            "period_return_percent": (
                str(artifact.period_return_percent)
                if artifact.period_return_percent is not None
                else None
            )
        },
        "benchmark": {
            "status": "unavailable",
            "limitation": "No benchmark was requested from the MCP market-data tool.",
        },
        "readiness": {},
        "evidence": [
            {
                "source": artifact.provider,
                "description": reference,
                "as_of": artifact.fetched_at.isoformat(),
            }
            for reference in artifact.evidence_refs
        ],
    }


class VibeMarketDataTool:
    def __init__(
        self,
        client: McpToolClient,
        settings: McpSettings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="get_vibe_market_data",
            description="Fetch bounded read-only market history through Vibe-Trading MCP.",
            executor=self.execute,
            owner="investment_research",
            deterministic=False,
        )

    async def execute(self, payload: dict[str, Any]) -> ToolObservation:
        started = perf_counter()
        context: AgentContext = payload["context"]
        reference = extract_instrument_reference(context.effective_message)
        if reference is None:
            return ToolObservation(
                tool_name="get_vibe_market_data",
                success=False,
                agent=str(payload.get("agent") or "cfo"),
                purpose="external_market_history",
                error_class="symbol_required",
                error_message="An explicit stock or ETF symbol is required.",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

        symbol, asset_type = reference
        provider_symbol = _provider_symbol(symbol)
        fetched_at = self.clock()
        date_to = fetched_at.date()
        date_from = date_to - timedelta(days=self.settings.lookback_days)
        arguments = {
            "codes": [provider_symbol],
            "start_date": date_from.isoformat(),
            "end_date": date_to.isoformat(),
            "source": self.settings.market_source,
            "interval": "1D",
            "max_rows": self.settings.max_rows,
        }
        try:
            response = await self.client.call_tool("get_market_data", arguments)
            artifact = normalize_market_history(
                response,
                symbol=symbol,
                provider_symbol=provider_symbol,
                asset_type=asset_type,
                date_from=date_from,
                date_to=date_to,
                source_requested=self.settings.market_source,
                max_rows=self.settings.max_rows,
                fetched_at=fetched_at,
            )
        except (McpClientError, ValueError, ArithmeticError) as exc:
            return ToolObservation(
                tool_name="get_vibe_market_data",
                success=False,
                agent=str(payload.get("agent") or "cfo"),
                purpose="external_market_history",
                error_class=type(exc).__name__,
                error_message="External MCP market evidence is unavailable.",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

        return ToolObservation(
            tool_name="get_vibe_market_data",
            success=True,
            agent=str(payload.get("agent") or "cfo"),
            purpose="external_market_history",
            result=artifact.model_dump(mode="json"),
            latency_ms=round((perf_counter() - started) * 1000, 2),
            evidence_refs=list(artifact.evidence_refs),
        )


def build_vibe_market_data_tool(settings: McpSettings) -> VibeMarketDataTool:
    return VibeMarketDataTool(build_mcp_client(settings), settings)
