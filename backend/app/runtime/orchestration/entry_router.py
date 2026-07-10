"""Finance-native pre-runtime conversation router.

This mirrors the Yili entry-router boundary: decide the top-level execution
path before runtime execution, without selecting tools or specialists.
"""

from __future__ import annotations

import re
from typing import Any

from app.models.routing import ConversationRoute, build_route


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


class EntryRouter:
    """Deterministic entry router for My Office chat turns."""

    def route(
        self,
        message: str,
        *,
        chat_history: list[dict[str, Any]] | None = None,
        memory_context: dict[str, Any] | None = None,
    ) -> ConversationRoute:
        del memory_context
        text = _normalize(message)
        if not text:
            return self._clarification("empty message")

        has_finance_signal = _contains_any(text, _FINANCE_PATTERNS)
        has_question_signal = _contains_any(text, _QUESTION_PATTERNS)
        has_followup_signal = _contains_any(text, _FOLLOW_UP_PATTERNS)
        has_prior_context = _has_history(chat_history)

        # Digits usually mean a fresh ledger question ("为什么6月10日花这么多"),
        # not a request for the previous answer's evidence.
        if (
            _contains_any(text, _EVIDENCE_PATTERNS)
            and not has_finance_signal
            and not _contains_digit(text)
            and has_prior_context
        ):
            return build_route(
                "evidence_request",
                "evidence_only",
                run_finance_pipeline=False,
                emit_steps=False,
                attach_evidence=True,
                memory_scope="session",
                response_mode="direct_answer",
                label="evidence request",
            )

        if has_prior_context and has_followup_signal and not has_finance_signal:
            return build_route(
                "follow_up",
                "cfo_followup",
                run_finance_pipeline=True,
                emit_steps=True,
                attach_evidence=True,
                memory_scope="finance_context",
                response_mode="analysis",
                label="contextual follow-up",
            )

        if has_finance_signal:
            return build_route(
                "finance_query",
                "cfo_followup" if has_prior_context and has_followup_signal else "cfo_analysis",
                run_finance_pipeline=True,
                emit_steps=True,
                attach_evidence=True,
                memory_scope="finance_context",
                response_mode="analysis",
                label="finance query",
            )

        if _is_acknowledgement(text):
            return build_route(
                "acknowledgement",
                "light_reply",
                run_finance_pipeline=False,
                emit_steps=False,
                attach_evidence=False,
                memory_scope="session",
                response_mode="light",
                label="acknowledgement",
            )

        if _is_greeting(text) or _looks_like_short_social_message(text):
            return build_route(
                "small_talk",
                "light_reply",
                run_finance_pipeline=False,
                emit_steps=False,
                attach_evidence=False,
                memory_scope="session",
                response_mode="light",
                label="small talk",
            )

        if has_question_signal:
            return self._clarification("non-finance question")

        return build_route(
            "unsupported",
            "clarification",
            run_finance_pipeline=False,
            emit_steps=False,
            attach_evidence=False,
            memory_scope="session",
            response_mode="ask_clarification",
            label="unsupported",
        )

    @staticmethod
    def _clarification(label: str) -> ConversationRoute:
        return build_route(
            "clarification",
            "clarification",
            run_finance_pipeline=False,
            emit_steps=False,
            attach_evidence=False,
            memory_scope="session",
            response_mode="ask_clarification",
            label=label,
        )
