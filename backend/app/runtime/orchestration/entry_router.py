"""Finance-native pre-runtime conversation router.

This mirrors the Yili entry-router boundary: decide the top-level execution
path before runtime execution, without selecting tools or specialists.
"""

from __future__ import annotations

import re
from time import perf_counter
from typing import Any, Protocol

from app.models.routing import (
    ConversationRoute,
    GuardReason,
    RouteCandidate,
    RouteDecision,
    route_for_path,
)


_WHITESPACE_RE = re.compile(r"\s+")
# Strip punctuation before social equality matching so "好的！" == "好的".
_PUNCTUATION_RE = re.compile(r"[\s,.!?;:~，。！？；：、…·\"'“”‘’()（）\[\]【】-]+")
# English greetings must lead the message as whole words; substring matching
# would fire on "this" (contains "hi").
_EN_GREETING_RE = re.compile(r"^(hi|hey|hello|yo)\b")

# Social matching is EXACT (after punctuation strip), never substring: single
# characters like "好"/"嗯" are substrings of countless real requests.
_GREETING_EXACT = {
    "你好",
    "您好",
    "早上好",
    "下午好",
    "晚上好",
    "早",
    "早安",
    "晚安",
    "hi",
    "hello",
    "hey",
    "yo",
    "在吗",
    "在不在",
    "哈喽",
    "嗨",
}

_GREETING_PREFIXES = ("你好", "您好", "哈喽", "嗨")

_ACK_EXACT = {
    "好的",
    "好",
    "好嘞",
    "好滴",
    "ok",
    "okay",
    "可以",
    "可以的",
    "嗯",
    "嗯嗯",
    "行",
    "收到",
    "明白",
    "明白了",
    "知道了",
    "了解",
    "谢谢",
    "谢啦",
    "多谢",
    "thanks",
    "thankyou",
    "thx",
    "哈哈",
    "hhh",
    "666",
    "赞",
    "nice",
}

# Pure-laughter/filler alphabets: any-length runs like 哈哈哈哈 stay social.
_FILLER_CHARS = {"哈", "嘿", "呵", "嗯", "哦", "噢", "喔", "额", "呃", "嗷"}

_EVIDENCE_PATTERNS = (
    "为什么",
    "依据",
    "证据",
    "引用",
    "来源",
    "怎么得出",
    "怎么算",
    "理由",
    "reason",
    "source",
    "evidence",
    "citation",
)

_FOLLOW_UP_PATTERNS = (
    "继续",
    "展开",
    "上面",
    "刚刚",
    "上一条",
    "这条",
    "这个",
    "这个建议",
    "这一天",
    "那天",
    "再看",
    "再看看",
    "详细",
    "具体",
)

_FINANCE_PATTERNS = (
    "钱",
    "财务",
    "财务健康",
    "健康检查",
    "账单",
    "流水",
    "交易",
    "消费",
    "支出",
    "收入",
    "预算",
    "现金流",
    "净现金流",
    "储蓄",
    "存钱",
    "购物",
    "餐饮",
    "吃饭",
    "外卖",
    "交通",
    "房租",
    "住房",
    "订阅",
    "会员",
    "重复",
    "异常",
    "分类",
    "类目",
    "商户",
    "导入",
    "数据质量",
    "支付宝",
    "微信",
    "银行",
    "工行",
    "花",
    "开销",
    "花销",
    "花费",
    "手头",
    "缺钱",
    "省钱",
    "攒钱",
    "存款",
    "余额",
    "工资",
    "薪水",
    "贷款",
    "房贷",
    "还款",
    "信用卡",
    "转账",
    "记账",
    "超支",
    "月光",
    "spend",
    "spending",
    "expense",
    "expenses",
    "finance",
    "financial",
    "financially",
    "health check",
    "income",
    "budget",
    "cashflow",
    "cash flow",
    "transaction",
    "transactions",
    "statement",
    "duplicate",
    "anomaly",
    "merchant",
    "category",
    "shopping",
    "dining",
    "rent",
)

_QUESTION_PATTERNS = (
    "多少",
    "占比",
    "怎么样",
    "如何",
    "分析",
    "帮我",
    "?",
    "？",
    "how",
    "what",
    "why",
    "analyze",
)


def _normalize(message: str) -> str:
    return _WHITESPACE_RE.sub(" ", (message or "").strip())


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def _contains_digit(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def _compact(text: str) -> str:
    return _PUNCTUATION_RE.sub("", text.lower())


def _has_history(chat_history: list[dict[str, Any]] | None) -> bool:
    return bool(chat_history)


def _is_acknowledgement(text: str) -> bool:
    compact = _compact(text)
    if not compact:
        return False
    if compact in _ACK_EXACT:
        return True
    # Any-length laughter/filler runs ("哈哈哈哈", "嗯嗯嗯") stay social.
    return set(compact) <= _FILLER_CHARS


def _is_greeting(text: str) -> bool:
    compact = _compact(text)
    if not compact:
        return False
    if compact in _GREETING_EXACT:
        return True
    if len(compact) <= 8 and compact.startswith(_GREETING_PREFIXES):
        return True
    # English greetings anchor to the start of the raw text as whole words.
    return bool(_EN_GREETING_RE.match(text.lower().strip()))


def _looks_like_short_social_message(text: str) -> bool:
    compact = text.replace(" ", "")
    if len(compact) > 8:
        return False
    if _contains_digit(compact):
        return False
    if _contains_any(compact, _QUESTION_PATTERNS):
        return False
    return True


def _excerpt(message: str, limit: int = 120) -> str:
    """Bounded message excerpt for the run ledger (data minimization)."""

    return " ".join((message or "").split())[:limit]


class RouteRules:
    """Deterministic routing rules, used at two points in the pipeline.

    `decisive()` runs BEFORE the classifier: clearly social and clearly
    financial messages get a rule candidate with no LLM involved, and only
    the ambiguous middle band (None) ever reaches the model. `fallback()`
    runs AFTER the classifier when it is unavailable or invalid, preserving
    the v1 deterministic tail.
    """

    def decisive(
        self,
        message: str,
        *,
        has_prior_context: bool,
    ) -> RouteCandidate | None:
        text = _normalize(message)
        if not text:
            return RouteCandidate(
                intent="clarification",
                execution_path="clarification",
                confidence=1.0,
                reason_code="empty_message",
                source="rule",
            )

        has_finance_signal = _contains_any(text, _FINANCE_PATTERNS)
        has_followup_signal = _contains_any(text, _FOLLOW_UP_PATTERNS)

        # Digits usually mean a fresh ledger question ("为什么6月10日花这么多"),
        # not a request for the previous answer's evidence.
        if (
            _contains_any(text, _EVIDENCE_PATTERNS)
            and not has_finance_signal
            and not _contains_digit(text)
            and has_prior_context
        ):
            return RouteCandidate(
                intent="evidence_request",
                execution_path="evidence_only",
                confidence=1.0,
                reason_code="evidence_request",
                source="rule",
            )

        if has_prior_context and has_followup_signal and not has_finance_signal:
            return RouteCandidate(
                intent="follow_up",
                execution_path="cfo_followup",
                confidence=1.0,
                reason_code="contextual_followup",
                source="rule",
            )

        if has_finance_signal:
            return RouteCandidate(
                intent="finance_query",
                execution_path=(
                    "cfo_followup"
                    if has_prior_context and has_followup_signal
                    else "cfo_analysis"
                ),
                confidence=1.0,
                reason_code="finance_signal",
                source="rule",
            )

        if _is_acknowledgement(text):
            return RouteCandidate(
                intent="acknowledgement",
                execution_path="light_reply",
                confidence=1.0,
                reason_code="exact_acknowledgement",
                source="rule",
            )

        if _is_greeting(text) or _looks_like_short_social_message(text):
            return RouteCandidate(
                intent="small_talk",
                execution_path="light_reply",
                confidence=1.0,
                reason_code="social_message",
                source="rule",
            )

        # Ambiguous band: no provable signal either way.
        return None

    def fallback(self, message: str) -> RouteCandidate:
        """Deterministic v1 tail when no classifier verdict is available."""

        text = _normalize(message)
        if _contains_any(text, _QUESTION_PATTERNS):
            return RouteCandidate(
                intent="clarification",
                execution_path="clarification",
                reason_code="non_finance_question",
                source="fallback",
            )
        return RouteCandidate(
            intent="unsupported",
            execution_path="clarification",
            reason_code="unsupported",
            source="fallback",
        )


class RouteGuard:
    """Deterministic final adjudication over routing candidates.

    Uses lexical and state facts only — never model confidence. The
    fallback direction is asymmetric: uncertainty escalates toward the
    finance pipeline, never down to small talk.
    """

    def adjudicate(
        self,
        candidate: RouteCandidate,
        *,
        message: str,
        has_prior_context: bool,
    ) -> tuple[ConversationRoute, GuardReason]:
        if candidate.source in ("rule", "fallback"):
            # Rule candidates are already fact-derived; nothing to overrule.
            route = route_for_path(
                candidate.intent, candidate.execution_path, label=candidate.reason_code
            )
            return route, f"{candidate.source}_decisive"

        text = _normalize(message)
        # Keyword check is defensive here: messages that reach the model have
        # no finance keywords by construction (RouteRules.decisive would have
        # taken them), so in practice only the digit check fires. The guard
        # still must not assume the pre-route ran.
        has_finance_signal = _contains_any(text, _FINANCE_PATTERNS) or _contains_digit(text)

        # Model undercalled a message that carries verifiable finance facts.
        if candidate.execution_path in ("light_reply", "clarification") and has_finance_signal:
            route = route_for_path("finance_query", "cfo_analysis", label="guard escalation")
            return route, "lexical_finance_override"

        # Model claims a finance intent but proposes a non-finance path.
        if (
            candidate.intent in ("finance_query", "follow_up")
            and candidate.execution_path in ("light_reply", "clarification")
        ):
            path = "cfo_followup" if has_prior_context and candidate.intent == "follow_up" else "cfo_analysis"
            route = route_for_path(candidate.intent, path, label="guard escalation")
            return route, "intent_path_mismatch"

        # Evidence needs something to point at.
        if candidate.execution_path == "evidence_only" and not has_prior_context:
            route = route_for_path("clarification", "clarification", label="guard downgrade")
            return route, "no_context_downgrade"

        # A follow-up without context is just a fresh question.
        if candidate.execution_path == "cfo_followup" and not has_prior_context:
            route = route_for_path("finance_query", "cfo_analysis", label="guard promotion")
            return route, "no_context_promotion"

        route = route_for_path(
            candidate.intent, candidate.execution_path, label=candidate.reason_code
        )
        return route, "model_accepted"


class RouteClassifier(Protocol):
    """Injected semantic classifier for the ambiguous band."""

    def available(self) -> bool: ...

    async def classify(
        self, message: str, *, has_prior_context: bool
    ) -> RouteCandidate | None: ...


class EntryRouter:
    """Hybrid entry router: RouteRules -> RouteClassifier -> RouteGuard.

    `route()` is the fully deterministic path (decisive rules + fallback)
    and stays synchronous for tests and offline evals. `decide()` is the
    runtime entrypoint; with no classifier configured it is behaviorally
    identical to `route()`.
    """

    def __init__(self, classifier: RouteClassifier | None = None):
        self.rules = RouteRules()
        self.guard = RouteGuard()
        self.classifier = classifier

    def route(
        self,
        message: str,
        *,
        chat_history: list[dict[str, Any]] | None = None,
        memory_context: dict[str, Any] | None = None,
    ) -> ConversationRoute:
        del memory_context
        has_prior_context = _has_history(chat_history)
        candidate = self.rules.decisive(
            message, has_prior_context=has_prior_context
        ) or self.rules.fallback(message)
        route, _ = self.guard.adjudicate(
            candidate, message=message, has_prior_context=has_prior_context
        )
        return route

    async def decide(
        self,
        message: str,
        *,
        chat_history: list[dict[str, Any]] | None = None,
        memory_context: dict[str, Any] | None = None,
    ) -> RouteDecision:
        del memory_context
        has_prior_context = _has_history(chat_history)
        candidate = self.rules.decisive(message, has_prior_context=has_prior_context)

        classifier_status = "skipped"
        classifier_latency_ms: float | None = None
        if (
            candidate is None
            and self.classifier is not None
            and self.classifier.available()
        ):
            started = perf_counter()
            model_candidate = await self.classifier.classify(
                message, has_prior_context=has_prior_context
            )
            classifier_latency_ms = round((perf_counter() - started) * 1000, 2)
            if model_candidate is not None:
                candidate = model_candidate
                classifier_status = "called"
            else:
                classifier_status = "failed"

        if candidate is None:
            candidate = self.rules.fallback(message)

        route, guard_reason = self.guard.adjudicate(
            candidate, message=message, has_prior_context=has_prior_context
        )
        return RouteDecision(
            route=route,
            candidate=candidate,
            guard_reason=guard_reason,
            message_excerpt=_excerpt(message),
            classifier_status=classifier_status,
            classifier_latency_ms=classifier_latency_ms,
        )
