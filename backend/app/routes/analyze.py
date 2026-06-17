"""/analyze endpoint backed by the OpenAI Agents SDK analysis runtime."""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models.analysis import AnalyzeRequest
from app.runtime.analysis_runtime import OpenAIAnalysisRuntime
from app.services.anomalies import detect_anomalies
from app.services.categorizer import enrich_transactions
from app.services.summaries import build_category_summary

logger = logging.getLogger(__name__)
router = APIRouter()
_runtime = OpenAIAnalysisRuntime()


@router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        txns = enrich_transactions(req.transactions)
        anomalies = detect_anomalies(txns)
        category_summary = build_category_summary(txns)
        payload = {
            "user_id": req.user_id,
            "monthly_totals": req.monthly_totals,
            "category_summary": category_summary,
            "anomalies": anomalies,
            "transactions_sample": txns[:30],
        }
        analysis = await _runtime.run(payload)
        return {
            "ok": True,
            "meta": {"user_id": req.user_id, "currency": "CNY"},
            "monthly_totals": req.monthly_totals,
            "category_summary": category_summary,
            "anomalies": anomalies,
            **analysis,
            "debug": {"rule_version": "v1", "model": "openai-agents-sdk"},
        }
    except Exception:
        logger.exception("Analysis failed for user=%s", req.user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Analysis failed"})
