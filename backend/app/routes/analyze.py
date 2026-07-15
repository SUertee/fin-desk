"""/analyze endpoint backed by the OpenAI Agents SDK analysis runtime."""

import logging
from datetime import date

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models.analysis import AnalyzeRequest, AnalyzeResponse
from app.agents.specialists.analysis_agent import analysis_agent_model_name
from app.config.settings import get_settings
from app.connectors.postgres.exchange_rate_store import get_exchange_rate_snapshot_db
from app.connectors.postgres.run_ledger_store import save_agent_run_record_db
from app.runtime.llm.openai_analysis_runtime import OpenAIAnalysisRuntime
from app.runtime.costing import CostingService
from app.runtime.contracts.output_validation import validate_output_contract
from app.runtime.observability.trace_collector import TraceCollector
from app.services.anomalies import detect_anomalies
from app.services.categorizer import enrich_transactions
from app.services.summaries import build_category_summary
from app.services.user_store import get_profile

logger = logging.getLogger(__name__)
router = APIRouter()
_runtime = OpenAIAnalysisRuntime()
_costing = CostingService(exchange_rate_lookup=get_exchange_rate_snapshot_db)


def _persist_trace(trace: TraceCollector) -> None:
    saved = save_agent_run_record_db(trace.to_run_record())
    if not saved:
        logger.debug("Agent run record was not persisted request_id=%s", trace.request_id)


def _finalize_trace_cost(trace: TraceCollector, user_id: str) -> None:
    profile = get_profile(user_id)
    trace.set_cost(
        _costing.cost_stage_entries(
            trace.policy.get("llm_usage_by_stage") or {},
            reporting_currency=profile.cost_preferences.reporting_currency,
            accounting_date=date.today(),
        )
    )


@router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    trace = TraceCollector.start_run(
        user_id=req.user_id,
        entrypoint="analyze",
        runtime_requested="openai",
    )
    trace.set_model_name(analysis_agent_model_name())
    trace.select_agents(["analysis_specialist"])
    trace.set_output_contract("AnalyzeResponse")
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
        trace.set_input_summary(
            {
                "transaction_count": len(req.transactions),
                "monthly_total_count": len(req.monthly_totals),
                "anomaly_count": len(anomalies),
            }
        )
        analysis = await _runtime.run(payload)
        observations = analysis.pop("_run_observations", None)
        if observations is not None:
            settings = get_settings()
            trace.record_observations(
                tool_calls=observations.tool_calls,
                handoffs=observations.handoffs,
                output_validations=observations.output_validations,
                usage=observations.usage,
            )
            trace.policy["llm_usage_by_stage"] = {
                "analysis": {
                    "status": "called",
                    "model_name": trace.model_name,
                    "profile": settings.analysis_model_profile,
                    **observations.usage.model_dump(mode="json"),
                }
            }
        trace.mark_runtime_used("openai")
        response_payload = {
            "ok": True,
            "meta": {"user_id": req.user_id, "currency": "CNY"},
            "monthly_totals": req.monthly_totals,
            "category_summary": category_summary,
            "anomalies": anomalies,
            **analysis,
            "debug": {"rule_version": "v1", "model": "openai-agents-sdk"},
        }
        _, validation = validate_output_contract(
            agent="analysis_specialist",
            contract="AnalyzeResponse",
            model_type=AnalyzeResponse,
            payload=response_payload,
        )
        trace.record_output_validation(validation)
        if validation.status == "failed":
            raise ValueError("Analysis route returned invalid AnalyzeResponse")
        _finalize_trace_cost(trace, req.user_id)
        logger.info("Analysis runtime trace", extra={"trace": trace.to_log_dict()})
        _persist_trace(trace)
        return response_payload
    except Exception as exc:
        trace.fail(exc)
        _finalize_trace_cost(trace, req.user_id)
        logger.info("Analysis runtime trace", extra={"trace": trace.to_log_dict()})
        _persist_trace(trace)
        logger.exception("Analysis failed for user=%s", req.user_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Analysis failed"})
