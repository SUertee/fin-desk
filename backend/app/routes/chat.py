"""
/chat endpoints - Multi-agent chat and history management.
"""

import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.connectors.postgres.transactions_store import (
    get_latest_analysis_run_db,
    list_transactions_db,
)
from app.models.chat import ChatRequest, ChatResponse
from app.runtime.memory import build_memory_context
from app.runtime.orchestration.finance_runtime import FinanceRuntime
from app.connectors.postgres.office_store import get_session_db, update_session_db
from app.services.memory import clear_history, get_chat_history, save_message
from app.services.user_store import get_profile

logger = logging.getLogger(__name__)
router = APIRouter()
_runtime = FinanceRuntime()


def _resolve_session(req: ChatRequest) -> tuple[str, JSONResponse | None]:
    """Return (session_id, error). Unknown sessions are a typed 404."""

    session_id = (req.session_id or "").strip()
    if not session_id:
        return "", None
    if get_session_db(req.user_id, session_id) is None:
        return "", JSONResponse(
            status_code=404, content={"ok": False, "error": "Unknown session"}
        )
    return session_id, None


def _persist_turns(
    user_id: str, session_id: str, message: str, reply: str, request_id: str
) -> None:
    save_message(user_id, "user", message, session_id=session_id)
    save_message(
        user_id, "assistant", reply, session_id=session_id, request_id=request_id
    )
    if session_id:
        session = get_session_db(user_id, session_id)
        updates: dict = {"last_message_preview": reply}
        if session and not (session.get("title") or "").strip():
            updates["title"] = " ".join(message.split())[:24]
        update_session_db(user_id, session_id, **updates)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        session_id, session_error = _resolve_session(req)
        if session_error is not None:
            return session_error
        txns = list_transactions_db(req.user_id, limit=2000)
        run = get_latest_analysis_run_db(req.user_id)
        monthly_totals = run.get("monthly_totals", []) if run else []
        profile = get_profile(req.user_id)
        chat_history = get_chat_history(req.user_id, session_id=session_id)
        memory_context = build_memory_context(
            user_id=req.user_id,
            chat_history=chat_history,
            session_id=session_id,
        )
        result = await _runtime.handle(
            user_id=req.user_id,
            message=req.message,
            profile=profile.model_dump(),
            transactions=txns,
            monthly_totals=monthly_totals,
            chat_history=chat_history,
            memory_context=memory_context.model_dump(),
            session_id=session_id,
        )
        _persist_turns(
            req.user_id, session_id, req.message, result["reply"],
            str(result.get("request_id") or ""),
        )
        return ChatResponse(**result)
    except Exception:
        logger.exception("Chat failed for user=%s", req.user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Internal server error"})


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE variant of /chat: `delta` events while the model generates, one
    `done` event with the full ChatResponse payload. The pipeline (policy →
    tools → specialists → audit) completes before streaming starts."""

    queue: asyncio.Queue = asyncio.Queue()

    async def on_delta(text: str) -> None:
        await queue.put({"type": "delta", "text": text})

    async def on_steps(steps: list) -> None:
        await queue.put({"type": "steps", "steps": steps})

    async def run() -> None:
        try:
            session_id, session_error = _resolve_session(req)
            if session_error is not None:
                await queue.put({"type": "error", "error": "Unknown session"})
                return
            txns = list_transactions_db(req.user_id, limit=2000)
            run_record = get_latest_analysis_run_db(req.user_id)
            monthly_totals = run_record.get("monthly_totals", []) if run_record else []
            profile = get_profile(req.user_id)
            chat_history = get_chat_history(req.user_id, session_id=session_id)
            memory_context = build_memory_context(
                user_id=req.user_id,
                chat_history=chat_history,
                session_id=session_id,
            )
            result = await _runtime.handle(
                user_id=req.user_id,
                message=req.message,
                profile=profile.model_dump(),
                transactions=txns,
                monthly_totals=monthly_totals,
                chat_history=chat_history,
                memory_context=memory_context.model_dump(),
                session_id=session_id,
                on_reply_delta=on_delta,
                on_pipeline_complete=on_steps,
            )
            _persist_turns(
                req.user_id, session_id, req.message, result["reply"],
                str(result.get("request_id") or ""),
            )
            payload = ChatResponse(**result).model_dump(mode="json")
            await queue.put({"type": "done", "response": payload})
        except Exception:
            logger.exception("Streaming chat failed for user=%s", req.user_id)
            await queue.put({"type": "error", "error": "Chat failed"})
        finally:
            await queue.put(None)

    async def event_stream():
        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
