"""
/chat endpoints - Multi-agent chat and history management.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.agents.orchestrator import handle_message
from app.repositories.transactions_repo import get_latest_analysis_run_db, list_transactions_db
from app.models.chat import ChatRequest, ChatResponse
from app.services.memory import clear_history, get_chat_history

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        txns = list_transactions_db(req.user_id, limit=200)
        run = get_latest_analysis_run_db(req.user_id)
        monthly_totals = run.get("monthly_totals", []) if run else []
        result = await handle_message(
            user_id=req.user_id,
            message=req.message,
            transactions=txns,
            monthly_totals=monthly_totals,
        )
        return ChatResponse(**result)
    except Exception:
        logger.exception("Chat failed for user=%s", req.user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Internal server error"})


@router.get("/chat/history/{user_id}")
def get_history(user_id: str, limit: int = 50):
    try:
        return {"user_id": user_id, "messages": get_chat_history(user_id, limit)}
    except Exception:
        logger.exception("Failed to get chat history for user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to retrieve chat history"})


@router.delete("/chat/history/{user_id}")
def delete_history(user_id: str):
    try:
        clear_history(user_id)
        return {"ok": True, "message": f"Chat history cleared for {user_id}"}
    except Exception:
        logger.exception("Failed to clear history for user=%s", user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to clear chat history"})
