"""Router eval regression floor.

The deterministic router must stay perfect on the provable categories
(social, false_trigger, evidence, finance). The ambiguous category is the
hybrid classifier's target band and carries no deterministic floor —
its baseline (0/6) is recorded by the overall floor.
"""

import pytest

from app.evals.router_eval import (
    deterministic_route_fn,
    load_router_cases,
    run_router_eval,
)

# Recorded deterministic baseline (2026-07-11): 29/35 overall,
# 100% on every category except ambiguous (0/6).
DETERMINISTIC_OVERALL_FLOOR = 29
PERFECT_CATEGORIES = ("social", "false_trigger", "evidence", "finance")


def test_router_case_set_covers_all_categories():
    cases = load_router_cases()
    categories = {case.case_id.split("_")[0] for case in cases}

    assert len(cases) >= 30
    assert {case.category for case in cases} == {
        "social",
        "false_trigger",
        "evidence",
        "finance",
        "ambiguous",
    }
    # case ids stay unique — duplicated ids would hide dropped cases
    assert len({case.case_id for case in cases}) == len(cases)
    del categories


@pytest.mark.asyncio
async def test_deterministic_router_holds_the_recorded_floor():
    report = await run_router_eval(deterministic_route_fn())

    for category in PERFECT_CATEGORIES:
        score = report.by_category[category]
        assert score.passed == score.total, (
            f"{category} regressed: "
            + "; ".join(
                f"{r.case_id}->{r.actual_path}"
                for r in report.failures()
                if r.category == category
            )
        )
    assert report.passed >= DETERMINISTIC_OVERALL_FLOOR
