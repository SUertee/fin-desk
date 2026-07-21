import asyncio

from app.evals.memory_eval import (
    MemoryEvalCase,
    MemoryEvalExpectation,
    evaluate_memory_case,
    load_memory_cases,
    run_memory_eval,
)


def test_memory_eval_fixture_is_complete_and_passes():
    cases = load_memory_cases()
    report = asyncio.run(run_memory_eval(cases))

    assert len(cases) == 17
    assert report.passed == report.total == 17
    assert report.accuracy == 1.0
    assert set(report.by_category) == {
        "clarification",
        "recent_window",
        "reference_resolution",
        "session_safety",
        "social_safety",
        "summary_policy",
    }
    assert all(score.accuracy == 1.0 for score in report.by_category.values())


def test_memory_eval_reports_actionable_failure():
    case = MemoryEvalCase(
        case_id="intentional-miss",
        category="recent_window",
        chat_history=[{"role": "user", "content": "actual"}],
        expected=MemoryEvalExpectation(recent_contents=["expected"]),
    )

    result = asyncio.run(evaluate_memory_case(case))

    assert result.passed is False
    assert "recent contents" in result.failures[0]
