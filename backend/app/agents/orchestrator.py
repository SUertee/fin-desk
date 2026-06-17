"""
Orchestrator Agent - stable public entrypoint for finance chat.
"""

import logging

from app.runtime.cfo_chat_runtime import FinanceTeamRuntime
from app.services.memory import get_chat_history, save_message
from app.services.user_store import get_profile

logger = logging.getLogger(__name__)

_runtime = FinanceTeamRuntime()


async def handle_message(
    user_id: str,
    message: str,
    transactions: list[dict] | None = None,
    monthly_totals: list[dict] | None = None,
) -> dict:
    profile = get_profile(user_id)
    chat_history = get_chat_history(user_id)
    try:
        result = await _runtime.handle(
            user_id=user_id,
            message=message,
            profile=profile.model_dump(),
            transactions=transactions or [],
            monthly_totals=monthly_totals or [],
            chat_history=chat_history,
        )
    except Exception:
        logger.exception("Finance runtime failed for user=%s", user_id)
        result = {
            "reply": "Sorry, something went wrong. Please try again.",
            "agent_used": "error",
            "data": None,
        }

    save_message(user_id, "user", message)
    save_message(user_id, "assistant", result["reply"])
    logger.info(
        "Handled message for user=%s, agent=%s",
        user_id,
        result.get("agent_used", "general"),
    )
    return result
