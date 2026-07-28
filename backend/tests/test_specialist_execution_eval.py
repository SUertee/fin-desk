import asyncio

from app.evals.specialist_execution_eval import (
    SpecialistExecutionEvalCase,
    SpecialistExecutionWorker,
    evaluate_specialist_execution_case,
    load_specialist_execution_cases,
    run_specialist_execution_eval,
)


def test_specialist_execution_eval_fixture_is_complete_and_passes():
    cases = load_specialist_execution_cases()
    report = asyncio.run(run_specialist_execution_eval(cases))

    assert {case.case_id for case in cases} == {
        "independent_parallel_speedup",
        "dependency_chain",
        "timeout_isolation",
        "non_parallel_tasks",
    }
    assert report.passed == report.total == 4
    speedup = next(
        result.speedup
        for result in report.results
        if result.case_id == "independent_parallel_speedup"
    )
    assert speedup is not None and speedup >= 1.5


def test_specialist_execution_eval_reports_actionable_status_failure():
    case = SpecialistExecutionEvalCase(
        case_id="intentional-status-miss",
        workers=[
            SpecialistExecutionWorker(
                task_id="expense",
                specialist="expense_analyst",
            )
        ],
        expected_statuses={"expense": "failed"},
    )

    result = asyncio.run(evaluate_specialist_execution_case(case))

    assert result.passed is False
    assert result.failures
    assert result.failures[0].startswith("statuses=")


def test_specialist_execution_eval_report_excludes_worker_payloads():
    report = asyncio.run(run_specialist_execution_eval())
    payload = report.model_dump()

    assert "evidence" not in str(payload).lower()
    assert "output" not in str(payload).lower()
    assert "prompt" not in str(payload).lower()
