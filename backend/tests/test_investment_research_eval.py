from app.evals.investment_research_eval import (
    load_investment_research_cases,
    run_investment_research_eval,
)


def test_investment_eval_covers_quality_and_safety_boundaries():
    cases = load_investment_research_cases()

    assert {case.case_id for case in cases} == {
        "grounded_performance",
        "stale_market_evidence",
        "missing_benchmark_and_readiness",
        "guarantee_and_trade_request",
    }


def test_investment_eval_baseline_is_fully_deterministic():
    report = run_investment_research_eval()

    assert report.passed == report.total, {
        item.case_id: item.failures for item in report.results if not item.passed
    }
