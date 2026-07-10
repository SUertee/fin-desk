"""Per-run memory context assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.runtime.memory.memory_policy import (
    DEFAULT_MAX_MESSAGES,
    DEFAULT_MAX_USER_TURNS,
    SUMMARY_THRESHOLD_USER_TURNS,
)
from app.runtime.memory.session_context import read_session_context


@dataclass(frozen=True)
class MemoryContext:
    recent_turns: tuple[dict[str, str], ...] = ()
    session_memory: dict[str, Any] | None = None
    truncated: bool = False
    recent_turns_used: bool = True
    summary_used: bool = False
    usage_reason: str = "recent_turns_only"

    @property
    def conversation_summary(self) -> str:
        return str((self.session_memory or {}).get("conversation_summary") or "").strip()

    def model_dump(self) -> dict[str, Any]:
        return {
            "recent_turns": list(self.recent_turns),
            "session_memory": self.session_memory or {},
            "truncated": self.truncated,
            "recent_turns_used": self.recent_turns_used,
            "summary_used": self.summary_used,
            "usage_reason": self.usage_reason,
        }

    def safe_meta(self) -> dict[str, Any]:
        return {
            "memory_recent_turns_count": len(self.recent_turns),
            "memory_session_state_present": bool(self.session_memory),
            "memory_truncated": self.truncated,
            "memory_summary_used": self.summary_used,
            "memory_usage_reason": self.usage_reason,
        }


def build_memory_context(
    *,
    user_id: str,
    chat_history: list[dict[str, Any]],
    session_id: str = "default",
    max_user_turns: int = DEFAULT_MAX_USER_TURNS,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> MemoryContext:
    cleaned = _clean_messages(chat_history)
    recent_turns = tuple(
        _last_complete_turns(
            cleaned,
            max_user_turns=max_user_turns,
            max_messages=max_messages,
        )
    )
    user_turn_count = sum(1 for message in cleaned if message.get("role") == "user")
    truncated = len(cleaned) > len(recent_turns)
    session_memory = read_session_context(user_id=user_id, session_id=session_id)
    summary = str((session_memory or {}).get("conversation_summary") or "").strip()
    summary_used = bool(summary and user_turn_count > SUMMARY_THRESHOLD_USER_TURNS)

    if summary_used and recent_turns:
        reason = "recent_turns_with_session_summary"
    elif recent_turns:
        reason = "recent_turns_only"
    elif summary_used:
        reason = "session_summary_only"
    else:
        reason = "empty_memory"

    return MemoryContext(
        recent_turns=recent_turns,
        session_memory=session_memory,
        truncated=truncated,
        recent_turns_used=bool(recent_turns),
        summary_used=summary_used,
        usage_reason=reason,
    )


def _clean_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        content = " ".join(str(message.get("content") or "").split())
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned


def _last_complete_turns(
    messages: list[dict[str, str]],
    *,
    max_user_turns: int,
    max_messages: int,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    user_turns = 0
    for message in reversed(messages):
        out.append(message)
        if message.get("role") == "user":
            user_turns += 1
        if user_turns >= max_user_turns and len(out) >= 2:
            break
        if len(out) >= max_messages:
            break
    out.reverse()
    return out[-max_messages:]
