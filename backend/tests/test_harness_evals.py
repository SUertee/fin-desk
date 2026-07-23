import logging

import pytest

from app.evals.replay import evaluate_run_record, load_eval_cases
from app.models.analysis import AnalyzeRequest
from app.routes import analyze as analyze_route
from app.runtime.orchestration.factory import build_finance_runtime
from tests.cfo_decision_fakes import execute


class FakeAnalysisRuntime:
    async def run(self, context):
        return {
            "insights": ["Cash flow is positive"],
            "actions": ["Keep monitoring fixed costs"],
            "budget": {"rules": ["Review recurring expenses"], "monthly_targets": {}},
            "notes": "",
        }


def _case(case_id):
    return {case.case_id: case for case in load_eval_cases()}[case_id]


@pytest.mark.asyncio
async def test_chat_spending_eval_matches_runtime_trace(caplog):
    case = _case("chat_spending_review")
    runtime = build_finance_runtime(decision_engine=execute("finance.expense_review"))
    caplog.set_level(logging.INFO, logger="app.runtime.orchestration.finance_runtime")

    await runtime.handle(user_id=case.user_id, **case.input)

    traces = [record.trace for record in caplog.records if hasattr(record, "trace")]
    result = evaluate_run_record(traces[-1], case)

    assert result.passed, result.failures


@pytest.mark.asyncio
async def test_chat_budget_eval_matches_runtime_trace(caplog):
    case = _case("chat_budget_plan")
    runtime = build_finance_runtime(decision_engine=execute("finance.budget_coaching"))
    caplog.set_level(logging.INFO, logger="app.runtime.orchestration.finance_runtime")

    await runtime.handle(user_id=case.user_id, **case.input)

    traces = [record.trace for record in caplog.records if hasattr(record, "trace")]
    result = evaluate_run_record(traces[-1], case)

    assert result.passed, result.failures


@pytest.mark.asyncio
async def test_chat_insufficient_data_eval_matches_runtime_trace(caplog):
    case = _case("chat_insufficient_data")
    runtime = build_finance_runtime(
        decision_engine=execute("finance.context", "finance.audit_review")
    )
    caplog.set_level(logging.INFO, logger="app.runtime.orchestration.finance_runtime")

    await runtime.handle(user_id=case.user_id, **case.input)

    traces = [record.trace for record in caplog.records if hasattr(record, "trace")]
    result = evaluate_run_record(traces[-1], case)

    assert result.passed, result.failures


@pytest.mark.asyncio
async def test_analyze_eval_matches_route_trace(monkeypatch, caplog):
    case = _case("analyze_cashflow_snapshot")
    monkeypatch.setattr(analyze_route, "_runtime", FakeAnalysisRuntime())
    caplog.set_level(logging.INFO, logger=analyze_route.logger.name)

    await analyze_route.analyze(
        AnalyzeRequest(
            user_id=case.user_id,
            transactions=case.input["transactions"],
            monthly_totals=case.input["monthly_totals"],
        )
    )

    traces = [record.trace for record in caplog.records if hasattr(record, "trace")]
    result = evaluate_run_record(traces[-1], case)

    assert result.passed, result.failures
