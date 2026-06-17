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
    monkeypatch.setattr(analyze_route, "_runtime", runtime)

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
