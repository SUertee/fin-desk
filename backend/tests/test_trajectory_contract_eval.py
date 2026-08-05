from app.evals.trajectory_contract_eval import (
    TrajectoryContractCase,
    evaluate_trajectory_contract_case,
    load_trajectory_contract_cases,
    run_trajectory_contract_eval,
)


def _case(case_id: str) -> TrajectoryContractCase:
    return next(
        case for case in load_trajectory_contract_cases() if case.case_id == case_id
    )


def _replace_step(
    case: TrajectoryContractCase,
    task_id: str,
    **updates,
) -> TrajectoryContractCase:
    steps = tuple(
        step.model_copy(update=updates) if step.task_id == task_id else step
        for step in case.steps
    )
    return case.model_copy(update={"steps": steps})


def test_reviewed_trajectory_contract_cases_pass():
    report = run_trajectory_contract_eval()

    assert report.total == 5
    assert report.passed == 5
    assert all(result.passed for result in report.results)


def test_direct_response_rejects_fabricated_execution_surface():
    case = _case("direct_response_without_execution")
    mutated = case.model_copy(
        update={
            "execution": case.execution.model_copy(
                update={"evidence_available": True}
            )
        }
    )

    result = evaluate_trajectory_contract_case(mutated)

    assert "unexpected_execution_surface" in result.failures


def test_dependency_graph_rejects_missing_reference_and_cycle():
    case = _case("parallel_team_evidence_join")
    missing = _replace_step(
        case,
        "audit.risk",
        depends_on=("specialist.missing",),
    )
    cycle = _replace_step(
        case,
        "tool.finance_context",
        depends_on=("compose.cfo",),
    )

    assert "invalid_dependency_graph" in evaluate_trajectory_contract_case(
        missing
    ).failures
    assert "invalid_dependency_graph" in evaluate_trajectory_contract_case(
        cycle
    ).failures


def test_context_scope_rejects_unallowed_key():
    case = _case("single_specialist_minimal_context")
    mutated = _replace_step(
        case,
        "specialist.expense_analyst",
        projected_context_keys=(
            "expense_snapshot",
            "reply_language",
            "full_chat_history",
        ),
    )

    result = evaluate_trajectory_contract_case(mutated)

    assert "context_scope_violation" in result.failures


def test_artifact_lineage_rejects_missing_current_run_artifact():
    case = _case("single_specialist_minimal_context")
    mutated = case.model_copy(update={"available_artifacts": ()})

    result = evaluate_trajectory_contract_case(mutated)

    assert "artifact_lineage_broken" in result.failures


def test_high_risk_case_rejects_missing_or_independent_audit():
    case = _case("high_risk_requires_audit")
    missing = case.model_copy(
        update={"steps": tuple(step for step in case.steps if step.kind != "audit")}
    )
    independent = _replace_step(case, "audit.risk", depends_on=())

    assert "missing_required_audit" in evaluate_trajectory_contract_case(
        missing
    ).failures
    assert "missing_required_audit" in evaluate_trajectory_contract_case(
        independent
    ).failures


def test_audit_and_compose_steps_cannot_be_parallel_safe():
    case = _case("high_risk_requires_audit")
    mutated = _replace_step(case, "audit.risk", parallel_safe=True)

    result = evaluate_trajectory_contract_case(mutated)

    assert "unsafe_parallel_declaration" in result.failures


def test_failed_worker_cannot_enter_final_evidence():
    case = _case("partial_failure_is_contained")
    mutated = case.model_copy(
        update={
            "accepted_specialists": ("expense_analyst", "budget_coach"),
            "final_evidence_specialists": ("expense_analyst", "budget_coach"),
        }
    )

    result = evaluate_trajectory_contract_case(mutated)

    assert "failed_output_exposed" in result.failures


def test_partial_failure_requires_rejection_and_disclosure():
    case = _case("partial_failure_is_contained")
    mutated = case.model_copy(
        update={"rejected_specialists": (), "limitations": ()}
    )

    result = evaluate_trajectory_contract_case(mutated)

    assert "partial_failure_not_disclosed" in result.failures


def test_execution_projection_must_match_recorded_evidence():
    case = _case("single_specialist_minimal_context")
    mutated = case.model_copy(
        update={
            "execution": case.execution.model_copy(
                update={"evidence_available": False}
            )
        }
    )

    result = evaluate_trajectory_contract_case(mutated)

    assert "execution_projection_mismatch" in result.failures


def test_report_is_bounded_and_excludes_worker_payloads():
    payload = run_trajectory_contract_eval().model_dump(mode="json")
    serialized = str(payload)

    assert set(payload) == {"total", "passed", "results"}
    assert "projected_context_keys" not in serialized
    assert "artifact://" not in serialized
    assert "full_chat_history" not in serialized
