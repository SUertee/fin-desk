from __future__ import annotations

from app.evals.financial_grounding_eval import (
    evaluate_financial_grounding_case,
    load_financial_grounding_cases,
    run_financial_grounding_eval,
)


def _case(case_id: str):
    return next(
        case for case in load_financial_grounding_cases() if case.case_id == case_id
    )


def test_reviewed_financial_grounding_cases_pass():
    report = run_financial_grounding_eval()

    assert report.total == 6
    assert report.passed == 6
    assert all(result.passed for result in report.results)


def test_numeric_claim_requires_explicitly_referenced_evidence():
    case = _case("grounded_amount_and_ratio").model_copy(update={"evidence_refs": ()})

    result = evaluate_financial_grounding_case(case)

    assert not result.passed
    assert result.failures == ["unsupported_numeric_claim"]


def test_required_evidence_cannot_be_silently_omitted():
    case = _case("grounded_amount_and_ratio").model_copy(
        update={"reply": "Shopping is unusually high.", "evidence_refs": ()}
    )

    result = evaluate_financial_grounding_case(case)

    assert not result.passed
    assert result.failures == ["missing_required_evidence"]


def test_numeric_and_date_mutations_are_rejected():
    amount_case = _case("grounded_amount_and_ratio").model_copy(
        update={"reply": "Shopping is CNY 999,999.00, or 22.7% of expenses."}
    )
    date_case = _case("grounded_statement_date").model_copy(
        update={"reply": "The imported statement coverage ends on 2026-07-31."}
    )

    amount_result = evaluate_financial_grounding_case(amount_case)
    date_result = evaluate_financial_grounding_case(date_case)

    assert amount_result.failures == ["unsupported_numeric_claim"]
    assert date_result.failures == ["unsupported_date_claim"]


def test_missing_current_run_artifact_rejects_specialist_evidence():
    case = _case("specialist_current_run_evidence")
    specialist = case.specialist_artifacts[0].model_copy(
        update={"artifact_refs": ("artifact://stale_snapshot",)}
    )
    mutated = case.model_copy(update={"specialist_artifacts": (specialist,)})

    result = evaluate_financial_grounding_case(mutated)

    assert not result.passed
    assert "unresolved_artifact_ref" in result.failures
    assert "specialist_evidence_rejected" in result.failures


def test_invalid_knowledge_citation_is_rejected():
    case = _case("reviewed_knowledge_citation").model_copy(
        update={"citation_ids": ("knowledge:missing-chunk",)}
    )

    result = evaluate_financial_grounding_case(case)

    assert not result.passed
    assert result.failures == ["invalid_knowledge_citation"]


def test_no_match_must_state_the_evidence_limit():
    case = _case("honest_knowledge_no_match").model_copy(
        update={"reply": "This policy definitely applies to your situation."}
    )

    result = evaluate_financial_grounding_case(case)

    assert not result.passed
    assert result.failures == ["dishonest_no_match"]


def test_conversation_must_not_surface_evidence_controls():
    case = _case("conversation_without_evidence").model_copy(
        update={
            "artifacts": {"hidden": {"status": "available"}},
            "evidence_refs": ("artifact://hidden",),
        }
    )

    result = evaluate_financial_grounding_case(case)

    assert not result.passed
    assert result.failures == ["unexpected_evidence_surface"]


def test_conversation_numbers_do_not_require_financial_evidence():
    case = _case("conversation_without_evidence").model_copy(
        update={"reply": "I can help with 3 kinds of finance questions."}
    )

    result = evaluate_financial_grounding_case(case)

    assert result.passed
    assert result.failures == []
