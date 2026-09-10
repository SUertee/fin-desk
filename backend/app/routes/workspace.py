"""Workspace brief endpoint: agent-produced summary for the product surface."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.connectors.postgres.transactions_store import (
    get_latest_analysis_run_db,
    list_transactions_db,
)
from app.models.workspace import BriefPeriod, WorkspaceBrief
from app.routes.chat import _runtime
from app.services.user_store import get_profile
from app.services.cash_plan import cash_plan_context

logger = logging.getLogger(__name__)
router = APIRouter()

# Fixed internal intent so brief and chat output can never diverge in shape:
# the brief runs the same orchestration path as /chat.
BRIEF_INTENT = (
    "Workspace brief: review current spending and budget status, "
    "then produce prioritized actions. 分析当前消费与预算状态并给出优先行动。"
)

# Ledger-versioned cache: composing a brief costs an LLM call, so an
# unchanged ledger must serve the cached brief instantly.
_brief_cache: dict[str, tuple[str, WorkspaceBrief]] = {}


def _ledger_version(transactions: list[dict]) -> str:
    latest_created = max(
        (str(t.get("created_at") or "") for t in transactions), default=""
    )
    return f"{len(transactions)}:{latest_created}"


@router.get("/workspace/brief/{user_id}", response_model=WorkspaceBrief)
async def get_workspace_brief(user_id: str):
    try:
        transactions = list_transactions_db(user_id, limit=2000)
        generated_at = datetime.now(timezone.utc).isoformat()
        if not transactions:
            return WorkspaceBrief(
                generated_at=generated_at,
                has_data=False,
            )

        plan_context = cash_plan_context(user_id)
        plan_version = (
            plan_context["plan"]["updated_at"]
            if plan_context["configured"]
            else "unconfigured"
        )
        version = f"{_ledger_version(transactions)}:{plan_version}"
        cached = _brief_cache.get(user_id)
        if cached and cached[0] == version:
            return cached[1]

        run = get_latest_analysis_run_db(user_id)
        monthly_totals = run.get("monthly_totals", []) if run else []
        profile = get_profile(user_id)
        profile_data = profile.model_dump()
        profile_data["cash_plan"] = plan_context
        result = await _runtime.handle(
            user_id=user_id,
            message=BRIEF_INTENT,
            profile=profile_data,
            transactions=transactions,
            monthly_totals=monthly_totals,
            chat_history=[],
            memory_context={},
            entrypoint="workspace_brief",
        )
        data = result.get("data") or {}
        dates = sorted(t["date"] for t in transactions)
        brief = WorkspaceBrief(
            request_id=result.get("request_id"),
            generated_at=generated_at,
            has_data=True,
            headline=str(result.get("reply") or ""),
            period=BriefPeriod.model_validate({"from": dates[0], "to": dates[-1]}),
            summary_cards=data.get("summary_cards") or [],
            actions=data.get("actions") or [],
            audit=data.get("audit"),
        )
        _brief_cache[user_id] = (version, brief)
        return brief
    except Exception:
        logger.exception("Workspace brief failed for user=%s", user_id)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to generate workspace brief"},
        )
