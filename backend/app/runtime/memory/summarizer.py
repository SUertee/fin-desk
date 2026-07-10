"""Deterministic conversation summarizer for session memory."""

from __future__ import annotations

from typing import Any

from app.runtime.memory.memory_policy import SUMMARY_MAX_CHARS


def build_conversation_summary(
    chat_history: list[dict[str, Any]],
    *,
    max_user_turns: int = 5,
) -> str:
    lines: list[str] = []
    user_turns = 0
    for message in reversed(chat_history or []):
        role = str(message.get("role") or "").strip()
        content = " ".join(str(message.get("content") or "").split())
        if role not in {"user", "assistant"} or not content:
            continue
        prefix = "User" if role == "user" else "Assistant"
        lines.append(f"{prefix}: {content[:180]}")
        if role == "user":
            user_turns += 1
        if user_turns >= max_user_turns:
            break
    lines.reverse()
    return "\n".join(lines)[-SUMMARY_MAX_CHARS:]
