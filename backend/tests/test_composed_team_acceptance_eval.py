from datetime import datetime, timezone

import pytest

from app.agents.specialists import REGISTRY
from app.agents.specialists.contracts import SpecialistInput
from app.config.settings import WebResearchSettings
from app.evals.composed_team_acceptance import (
    build_composed_team_acceptance_report,
    evaluate_composed_team_acceptance_case,
    load_composed_team_acceptance_cases,
)
from app.models.web_research import (
    WebSearchProviderItem,
    WebSearchProviderResult,
    WebSearchProviderStatus,
)
from app.runtime.execution.specialist_runner import SpecialistRunner
from app.runtime.orchestration.factory import build_finance_runtime
from app.services.web_research import WebResearchService
from tests.cfo_decision_fakes import execute


NOW = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


class AcceptanceWebProvider:
    def get_status(self):
        return WebSearchProviderStatus(
            availability="available",
            configured_provider="acceptance-fixture",
            allowed=True,
        )

    def search(self, query, *, domains, max_results, topic, fetched_at):
        return WebSearchProviderResult(
            provider="acceptance-fixture",
            query=query,
            fetched_at=fetched_at,
            items=[
                WebSearchProviderItem(
                    title="Reviewed market update",
                    url="https://policy.example.gov/market-update",
                    snippet="Reviewed market context for an offline acceptance case.",
                    published_at=NOW,
                    score=0.9,
                )
            ],
        )


def _web_research_service() -> WebResearchService:
    settings = WebResearchSettings(
        provider="acceptance-fixture",
        allowed_providers=("acceptance-fixture",),
        allowed_domains=("example.gov",),
        max_results=3,
        outbound_call_budget=1,
    )
    return WebResearchService(
        AcceptanceWebProvider(),
        settings=settings,
        cache_reader=lambda *_args, **_kwargs: None,
        cache_writer=lambda _entry: True,
        clock=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_composed_team_acceptance_fixture_passes_offline(monkeypatch):
    from app.runtime.execution import finance_toolset
    from app.runtime.orchestration import finance_runtime

    saved_records = []
    monkeypatch.setattr(
        finance_runtime,
        "save_agent_run_record_db",
        lambda record: saved_records.append(record) or True,
    )
    monkeypatch.setattr(
        finance_runtime,
        "write_session_context",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        finance_toolset,
        "list_latest_quality_reports_db",
        lambda user_id: [],
    )

    results = []
    for case in load_composed_team_acceptance_cases():
        saved_records.clear()
        captured_inputs: dict[str, SpecialistInput] = {}

        def wrap(specialist):
            implementation = REGISTRY[specialist]

            def run(specialist_input: SpecialistInput):
                captured_inputs[specialist] = specialist_input
                if specialist in case.failing_specialists:
                    raise RuntimeError(f"Injected failure: {specialist}")
                return implementation(specialist_input)

            return run

        runner = SpecialistRunner(
            registry={name: wrap(name) for name in REGISTRY}
        )
        runtime = build_finance_runtime(
            decision_engine=execute(case.team_capability_id),
            specialist_runner=runner,
            web_research_service=_web_research_service(),
            llm_client=None,
        )
        response = await runtime.handle(
            user_id="acceptance-user",
            chat_history=[],
            memory_context={},
            **case.input.model_dump(),
        )

        assert len(saved_records) == 1
        results.append(
            evaluate_composed_team_acceptance_case(
                case,
                response,
                saved_records[0],
                captured_inputs,
            )
        )

    report = build_composed_team_acceptance_report(results)
    assert report.passed == report.total == 3, [
        (item.case_id, item.failures) for item in report.results
    ]


def test_composed_team_acceptance_report_is_bounded():
    result = evaluate_composed_team_acceptance_case
    report = build_composed_team_acceptance_report([])

    assert callable(result)
    assert report.model_dump() == {
        "total": 0,
        "passed": 0,
        "results": [],
    }
