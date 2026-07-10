from app.routes.evals import list_eval_cases, run_evals


def test_list_eval_cases_returns_fixture_summaries():
    result = list_eval_cases()

    assert result["ok"] is True
    case_ids = {item["case_id"] for item in result["cases"]}
    assert "chat_spending_review" in case_ids
    assert "chat_budget_plan" in case_ids


def test_run_evals_returns_sample_summary():
    result = run_evals()

    assert result["ok"] is True
    assert result["total"] >= 1
    assert result["passed"] >= 1
    assert result["failed"] == 0
    assert result["results"][0]["case_id"] == "chat_spending_review"
