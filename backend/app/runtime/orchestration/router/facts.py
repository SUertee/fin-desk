"""Deterministic fact extraction for entry routing.

All lexical and state facts are derived ONCE per message into a frozen
`MessageFacts`. Every routing stage (rule shortcuts, model classifier
input, route resolver) reads the same facts — no stage re-parses the raw
message, so consistency holds by construction. Facts describe the message;
they never decide an execution path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

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


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def _is_exact_acknowledgement(compact: str) -> bool:
    if not compact:
        return False
    if compact in _ACK_EXACT:
        return True
    return set(compact) <= _FILLER_CHARS


def _is_exact_greeting(compact: str, normalized: str) -> bool:
    if not compact:
        return False
    if compact in _GREETING_EXACT:
        return True
    if len(compact) <= 8 and compact.startswith(_GREETING_PREFIXES):
        return True
    # English greetings anchor to the start of the raw text as whole words.
    return bool(_EN_GREETING_RE.match(normalized.lower()))


def excerpt(message: str, limit: int = 120) -> str:
    """Bounded message excerpt for prompts and the run ledger."""

    return " ".join((message or "").split())[:limit]


@dataclass(frozen=True)
class MessageFacts:
    """Verifiable lexical and state facts about one chat turn."""

    normalized_text: str
    compact_text: str
    is_empty: bool
    has_digits: bool
    has_question_signal: bool
    has_finance_signal: bool
    has_followup_signal: bool
    has_evidence_signal: bool
    has_prior_chat_history: bool
    has_prior_finance_context: bool
    is_short_social_shape: bool
    is_exact_greeting: bool
    is_exact_acknowledgement: bool

    @classmethod
    def from_message(
        cls,
        message: str,
        chat_history: list[dict[str, Any]] | None = None,
        memory_context: dict[str, Any] | None = None,
    ) -> "MessageFacts":
        normalized = _WHITESPACE_RE.sub(" ", (message or "").strip())
        compact = _PUNCTUATION_RE.sub("", normalized.lower())
        has_digits = any(ch.isdigit() for ch in compact)
        has_question = _contains_any(normalized, _QUESTION_PATTERNS)
        history = chat_history or []
        session_memory = (memory_context or {}).get("session_memory") or {}
        # Finance context requires verifiable provenance: session_memory is
        # written ONLY after a finance pipeline run (finance_runtime.
        # _write_memory), so its fields prove a prior CFO analysis exists.
        # A plain assistant turn in chat_history proves nothing — capability
        # intros and small talk are assistant messages too, and history rows
        # carry no route metadata to distinguish them. Never guess finance
        # context from raw assistant text.
        has_finance_context = bool(
            session_memory.get("last_topic")
            or session_memory.get("last_result_brief")
            # conversation_summary shares the same single writer (the finance
            # pipeline), so its presence is equally finance-provenanced.
            or session_memory.get("conversation_summary")
        )
        return cls(
            normalized_text=normalized,
            compact_text=compact,
            is_empty=not normalized,
            has_digits=has_digits,
            has_question_signal=has_question,
            has_finance_signal=_contains_any(normalized, _FINANCE_PATTERNS),
            has_followup_signal=_contains_any(normalized, _FOLLOW_UP_PATTERNS),
            has_evidence_signal=_contains_any(normalized, _EVIDENCE_PATTERNS),
            has_prior_chat_history=bool(history),
            has_prior_finance_context=has_finance_context,
            is_short_social_shape=(
                bool(compact)
                and len(normalized.replace(" ", "")) <= 8
                and not has_digits
                and not _contains_any(normalized.replace(" ", ""), _QUESTION_PATTERNS)
            ),
            is_exact_greeting=_is_exact_greeting(compact, normalized),
            is_exact_acknowledgement=_is_exact_acknowledgement(compact),
        )
