"""Agent eval endpoints for fixtures and replay metadata."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.evals.eval_runner import run_sample_evals
from app.evals.replay import load_eval_cases

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evals", tags=["evals"])


@router.get("/cases")
def list_eval_cases():
    try:
        cases = load_eval_cases()
        return {
            "ok": True,
            "cases": [
                {
                    "case_id": case.case_id,
                    "entrypoint": case.entrypoint,
                    "user_id": case.user_id,
                    "expected": case.expected.model_dump(mode="json"),
                }
                for case in cases
            ],
        }
    except Exception:
        logger.exception("Failed to list eval cases")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to list eval cases"},
        )


@router.post("/run")
def run_evals():
    try:
        summary = run_sample_evals()
        return summary.model_dump(mode="json")
    except Exception:
        logger.exception("Failed to run evals")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to run evals"},
        )
