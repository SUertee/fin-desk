"""Optional LLM wording over the deterministic CFO response."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

from app.models.runtime import AgentRunUsage
from app.runtime.policy.investment_policy import investment_output_violations

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CfoReplyResult:
    status: str
    reply: str | None = None
    usage: AgentRunUsage | None = None
    model_name: str | None = None
    latency_ms: float | None = None
    policy_violations: tuple[str, ...] = ()


class CfoReplyGenerator:
    """Generate grounded prose without owning runtime state or trace."""

    def __init__(
        self,
        client_provider: Callable[[], Any],
        language_resolver: Callable[[dict[str, Any], str], str],
    ) -> None:
        self._client_provider = client_provider
        self._language_resolver = language_resolver

    async def generate(
        self,
        *,
        context: dict[str, Any],
        message: str,
        effective_message: str,
        response_payload: dict[str, Any],
        on_reply_delta=None,
    ) -> CfoReplyResult:
        client = self._client_provider()
        if not client or not getattr(
            client,
            "available",
            lambda *_: False,
        )("chat"):
            return CfoReplyResult(status="skipped")

        started = perf_counter()
        try:
            digest = self._evidence_digest(context, response_payload)
            preferences = (
                (context.get("profile") or {}).get("preferences") or {}
            )
            language = self._language_resolver(preferences, message)
            tone = str(
                preferences.get("response_tone") or "balanced"
            )
            system = (
                "You are the CFO of the user's personal finance workspace. "
                "Answer ONLY from the evidence digest — never invent numbers, "
                "dates, or merchants that are not present in it. If the "
                "evidence cannot answer the question, say so plainly. "
                "When share_of_scope is null, say the percentage is unavailable; "
                "never report it as 0%. "
                "Reviewed knowledge is general guidance; never present it as "
                "the user's ledger data or individualized financial advice. "
                "No investment, tax, or legal advice. "
                "Write plain conversational prose. Do NOT add pseudo-structure "
                "labels or headings such as 核心洞察/关键发现/总结/建议 — the "
                "product renders findings and actions separately from typed data. "
                + (
                    "Reply in Chinese. "
                    if language == "zh"
                    else "Reply in English. "
                )
                + {
                    "concise": "Keep it to 1-2 sentences.",
                    "comprehensive": (
                        "Explain thoroughly with the key figures."
                    ),
                }.get(
                    tone,
                    "Keep it focused: lead with the answer, then one insight.",
                )
            )
            interpreted = (
                f"Interpreted as: {effective_message}\n\n"
                if effective_message and effective_message != message
                else ""
            )
            prompt = (
                f"User message: {message}\n\n"
                + interpreted
                + f"Evidence digest:\n{digest}\n\n"
                + "Compose the CFO reply."
            )
            investment_guard_enabled = bool(
                context.get("investment_research")
            )
            team_limitations = tuple(
                str(item)
                for item in context.get("team_execution_limitations") or ()
            )
            buffered_output_required = bool(
                investment_guard_enabled or team_limitations
            )
            if (
                on_reply_delta is not None
                and hasattr(client, "generate_text_stream")
                and not buffered_output_required
            ):
                result = await client.generate_text_stream(
                    prompt,
                    profile="chat",
                    system=system,
                    on_delta=on_reply_delta,
                )
            else:
                result = await client.generate_text(
                    prompt,
                    profile="chat",
                    system=system,
                )

            latency_ms = round((perf_counter() - started) * 1000, 2)
            status = "called" if result.content else "empty_content"
            reply = result.content or None
            violations: tuple[str, ...] = ()
            if result.content and investment_guard_enabled:
                violations = investment_output_violations(result.content)
                if violations:
                    status = "policy_blocked"
                    reply = None

            if reply and team_limitations:
                limitation = team_limitations[0]
                if limitation not in reply:
                    label = "数据限制：" if language == "zh" else "Coverage limitation: "
                    reply = f"{reply.rstrip()}\n\n{label}{limitation}"

            if on_reply_delta is not None and buffered_output_required:
                emitted = on_reply_delta(
                    reply or str(response_payload.get("reply") or "")
                )
                if hasattr(emitted, "__await__"):
                    await emitted

            return CfoReplyResult(
                status=status,
                reply=reply,
                usage=result.usage,
                model_name=result.model_name,
                latency_ms=latency_ms,
                policy_violations=violations,
            )
        except Exception as exc:
            logger.warning(
                "LLM compose failed; deterministic reply kept: %s",
                exc,
            )
            return CfoReplyResult(
                status="failed",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

    @staticmethod
    def _evidence_digest(
        context: dict[str, Any],
        response_payload: dict[str, Any],
    ) -> str:
        expense = context.get("expense_snapshot", {})
        budget = context.get("budget_snapshot", {})
        data = response_payload.get("data") or {}
        digest = {
            "typed_query_result": context.get("transaction_query"),
            "reviewed_knowledge": [
                {
                    key: item.get(key)
                    for key in (
                        "title",
                        "section",
                        "excerpt",
                        "source_url",
                        "source_authority",
                        "jurisdiction",
                        "reviewed_at",
                        "review_after",
                        "freshness",
                    )
                }
                for item in (
                    context.get("knowledge_retrieval") or {}
                ).get("artifacts", [])
            ],
            "knowledge_match_status": (
                context.get("knowledge_retrieval") or {}
            ).get("match_status"),
            "investment_research": context.get("investment_research"),
            "external_market_history": context.get(
                "external_market_history"
            ),
            "expense_snapshot": {
                "expense_total": expense.get("expense_total"),
                "income_total": expense.get("income_total"),
                "net_total": expense.get("net_total"),
                "transaction_count": expense.get("transaction_count"),
                "top_categories": (
                    expense.get("top_categories") or []
                )[:5],
                "anomaly_count": len(expense.get("anomalies") or []),
            },
            "budget_snapshot": budget,
            "findings": data.get("findings"),
            "actions": data.get("actions"),
            "audit": data.get("audit"),
            "import_quality_warnings": [
                warning
                for report in (
                    context.get("import_quality") or {}
                ).get("reports", [])
                for warning in report.get("warnings", [])
            ][:3],
        }
        return json.dumps(digest, ensure_ascii=False, default=str)
