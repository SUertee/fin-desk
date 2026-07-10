import pytest

from app.models.analysis import AnalyzeRequest
from app.routes import analyze as analyze_route


class FakeAnalysisRuntime:
    def __init__(self):
        self.context = None

    async def run(self, context):
        self.context = context
        return {
            "insights": ["Cash flow is positive"],
            "actions": ["Review dining spend"],
            "budget": {"rules": ["Keep dining under target"], "monthly_targets": {}},
            "notes": "",
        }


@pytest.mark.asyncio
async def test_analyze_route_uses_openai_analysis_runtime(monkeypatch):
    runtime = FakeAnalysisRuntime()
    monkeypatch.setenv("OPENAI_ANALYSIS_MODEL", "gpt-analysis-cost")
    monkeypatch.setenv("OPENAI_ANALYSIS_INPUT_COST_PER_1M", "0.5")
    monkeypatch.setenv("OPENAI_ANALYSIS_OUTPUT_COST_PER_1M", "1.5")
    saved_records = []
    monkeypatch.setattr(analyze_route, "_runtime", runtime)
    monkeypatch.setattr(
        analyze_route,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )

    result = await analyze_route.analyze(
        AnalyzeRequest(
            user_id="demo",
            monthly_totals=[{"month": "2026-06", "net": 1200}],
            transactions=[
                {"description": "Cafe", "amount": -12},
                {"description": "Salary", "amount": 5000},
            ],
        )
    )

    assert result["ok"] is True
    assert result["debug"]["model"] == "openai-agents-sdk"
    assert result["insights"] == ["Cash flow is positive"]
    assert runtime.context["user_id"] == "demo"
    assert runtime.context["transactions_sample"][0]["category"] == "dining"
    assert runtime.context["category_summary"]["by_category"][0]["category"] == "dining"
    assert saved_records[0].entrypoint == "analyze"
    assert saved_records[0].model_name == "gpt-analysis-cost"
    assert saved_records[0].output_contract == "AnalyzeResponse"
    assert saved_records[0].output_validations[0].status == "passed"
    assert saved_records[0].output_validations[0].contract == "AnalyzeResponse"
    assert saved_records[0].input_summary.transaction_count == 2
    assert saved_records[0].cost.pricing_source == "env_per_1m_tokens"


@pytest.mark.asyncio
async def test_analyze_route_persists_output_validation_failure(monkeypatch):
    class InvalidAnalysisRuntime:
        async def run(self, context):
            return {
                "insights": "not a list",
                "actions": ["Review dining spend"],
                "budget": {"rules": [], "monthly_targets": {}},
                "notes": "",
            }

    saved_records = []
    monkeypatch.setattr(analyze_route, "_runtime", InvalidAnalysisRuntime())
    monkeypatch.setattr(
        analyze_route,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )

    result = await analyze_route.analyze(
        AnalyzeRequest(
            user_id="demo",
            monthly_totals=[],
            transactions=[{"description": "Cafe", "amount": -12}],
        )
    )

    assert result.status_code == 500
    assert saved_records[0].runtime_used == "openai"
    assert saved_records[0].error_type == "ValueError"
    assert saved_records[0].output_validations[0].status == "failed"
    assert saved_records[0].output_validations[0].contract == "AnalyzeResponse"
    assert "insights:" in saved_records[0].output_validations[0].errors[0]
