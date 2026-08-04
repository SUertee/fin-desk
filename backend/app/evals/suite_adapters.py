"""Adapters from domain eval suites to the shared harness contract."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import isawaitable
from typing import Any, Callable, Iterator, Sequence

from app.agents.cfo.decision import (
    CapabilityRequest,
    CfoDecisionResult,
    CfoTurnDecision,
)
from app.agents.specialists import REGISTRY
from app.agents.specialists.contracts import SpecialistInput
from app.config.settings import WebResearchSettings
from app.evals.cfo_runtime_acceptance import (
    build_cfo_runtime_acceptance_report,
    evaluate_cfo_runtime_acceptance_case,
    load_cfo_runtime_acceptance_cases,
)
from app.evals.composed_team_acceptance import (
    build_composed_team_acceptance_report,
    evaluate_composed_team_acceptance_case,
    load_composed_team_acceptance_cases,
)
from app.evals.contracts import (
    OFFLINE_TRIAL_LIMITS,
    EvalCaseResult,
    EvalGraderResult,
    EvalSeverity,
    EvalSuiteReport,
    EvalTask,
    EvalTrial,
)
from app.evals.investment_research_eval import run_investment_research_eval
from app.evals.knowledge_retrieval_eval import (
    KnowledgeRetrievalEvalCase,
    load_knowledge_retrieval_cases,
    run_knowledge_retrieval_eval,
)
from app.evals.memory_eval import run_memory_eval
from app.evals.specialist_execution_eval import run_specialist_execution_eval
from app.knowledge import (
    KnowledgeQuery,
    KnowledgeRetrievalResult,
    build_knowledge_evidence,
)
from app.knowledge.markdown_ingestion import DEFAULT_CORPUS, parse_markdown_file
from app.models.web_research import (
    WebSearchProviderItem,
    WebSearchProviderResult,
    WebSearchProviderStatus,
)
from app.runtime.execution.specialist_runner import SpecialistRunner
from app.runtime.orchestration.factory import build_finance_runtime
from app.services.web_research import WebResearchService


@dataclass(frozen=True)
class _Observation:
    case_id: str
    passed: bool
    failure_count: int = 0
    errored: bool = False
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvalSuiteAdapter:
    suite_id: str
    fixture_ref: str
    severity: EvalSeverity
    run: Callable[[], Any]


class _StaticDecisionEngine:
    def __init__(self, decision: CfoTurnDecision) -> None:
        self._result = CfoDecisionResult(status="called", decision=decision)

    async def decide(self, *_args: Any, **_kwargs: Any) -> CfoDecisionResult:
        return self._result


class _NoMatchKnowledgeRetriever:
    def retrieve(self, query: KnowledgeQuery) -> KnowledgeRetrievalResult:
        return KnowledgeRetrievalResult(
            query=query.text,
            match_status="no_match",
            artifacts=[],
        )


class _FixtureKnowledgeRetriever:
    """Return reviewed corpus evidence selected by the eval fixture."""

    def __init__(self, cases: Sequence[KnowledgeRetrievalEvalCase]) -> None:
        self._cases = {_query_key(case): case for case in cases}
        self._corpus = {
            bundle.document.document_id: bundle
            for bundle in (
                parse_markdown_file(path) for path in sorted(DEFAULT_CORPUS.glob("*.md"))
            )
        }

    def retrieve(self, query: KnowledgeQuery) -> KnowledgeRetrievalResult:
        case = self._cases.get(_knowledge_query_key(query))
        if case is None or not case.expected_match:
            return KnowledgeRetrievalResult(
                query=query.text,
                match_status="no_match",
                artifacts=[],
            )

        document_id = next(
            (
                candidate
                for candidate in case.acceptable_document_ids
                if candidate in self._corpus
                and _document_allowed(self._corpus[candidate].document, query)
            ),
            None,
        )
        if document_id is None:
            return KnowledgeRetrievalResult(
                query=query.text,
                match_status="no_match",
                artifacts=[],
            )
        bundle = self._corpus[document_id]
        artifact = build_knowledge_evidence(
            bundle.document,
            bundle.chunks[0],
            retrieval_method="lexical",
            score=1.0,
            as_of=query.as_of,
        )
        return KnowledgeRetrievalResult(
            query=query.text,
            match_status="matched",
            artifacts=[artifact],
        )


class _AcceptanceWebProvider:
    def get_status(self) -> WebSearchProviderStatus:
        return WebSearchProviderStatus(
            availability="available",
            configured_provider="eval-fixture",
            allowed=True,
        )

    def search(
        self,
        query: str,
        *,
        domains: list[str],
        max_results: int,
        topic: str,
        fetched_at: datetime,
    ) -> WebSearchProviderResult:
        del domains, max_results, topic
        return WebSearchProviderResult(
            provider="eval-fixture",
            query=query,
            fetched_at=fetched_at,
            items=[
                WebSearchProviderItem(
                    title="Reviewed market update",
                    url="https://policy.example.gov/market-update",
                    snippet="Reviewed market context for an offline eval fixture.",
                    published_at=fetched_at,
                    score=0.9,
                )
            ],
        )


def _fixture_web_research_service() -> WebResearchService:
    now = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    return WebResearchService(
        _AcceptanceWebProvider(),
        settings=WebResearchSettings(
            provider="eval-fixture",
            allowed_providers=("eval-fixture",),
            allowed_domains=("example.gov",),
            max_results=3,
            outbound_call_budget=1,
        ),
        cache_reader=lambda *_args, **_kwargs: None,
        cache_writer=lambda _entry: True,
        clock=lambda: now,
    )


@contextmanager
def _isolated_runtime_storage() -> Iterator[list[Any]]:
    from app.runtime.execution import finance_toolset
    from app.runtime.orchestration import finance_runtime

    saved_records: list[Any] = []
    original_save = finance_runtime.save_agent_run_record_db
    original_write = finance_runtime.write_session_context
    original_reports = finance_toolset.list_latest_quality_reports_db
    finance_runtime.save_agent_run_record_db = (
        lambda record: saved_records.append(record) or True
    )
    finance_runtime.write_session_context = lambda **_kwargs: None
    finance_toolset.list_latest_quality_reports_db = lambda _user_id: []
    try:
        yield saved_records
    finally:
        finance_runtime.save_agent_run_record_db = original_save
        finance_runtime.write_session_context = original_write
        finance_toolset.list_latest_quality_reports_db = original_reports


async def _run_cfo_acceptance() -> list[_Observation]:
    cases = load_cfo_runtime_acceptance_cases()
    results = []
    with _isolated_runtime_storage() as saved_records:
        for case in cases:
            saved_records.clear()
            try:
                decision = CfoTurnDecision(
                    action=case.decision.action,
                    reply=case.decision.reply,
                    capability_requests=[
                        CapabilityRequest(capability_id=capability_id)
                        for capability_id in case.decision.capability_ids
                    ],
                )
                runtime = build_finance_runtime(
                    decision_engine=_StaticDecisionEngine(decision),
                    granted_capabilities=(
                        set(case.granted_capabilities)
                        if case.granted_capabilities is not None
                        else None
                    ),
                    knowledge_retriever=_NoMatchKnowledgeRetriever(),
                    web_research_service=_fixture_web_research_service(),
                    llm_client=None,
                )
                response = await runtime.handle(
                    user_id=case.user_id,
                    **case.input.model_dump(),
                )
                if len(saved_records) != 1:
                    raise RuntimeError("runtime did not persist exactly one run record")
                results.append(
                    evaluate_cfo_runtime_acceptance_case(
                        case,
                        response,
                        saved_records[0],
                    )
                )
            except Exception:
                results.append(None)
    observations = [
        _observation(case.case_id, result, tags=(case.category,))
        for case, result in zip(cases, results, strict=True)
    ]
    if all(result is not None for result in results):
        build_cfo_runtime_acceptance_report(results)  # type: ignore[arg-type]
    return observations


async def _run_composed_team_acceptance() -> list[_Observation]:
    cases = load_composed_team_acceptance_cases()
    results = []
    with _isolated_runtime_storage() as saved_records:
        for case in cases:
            saved_records.clear()
            captured_inputs: dict[str, SpecialistInput] = {}

            def wrap(specialist: str):
                implementation = REGISTRY[specialist]

                def run(specialist_input: SpecialistInput):
                    captured_inputs[specialist] = specialist_input
                    if specialist in case.failing_specialists:
                        raise RuntimeError(f"Injected fixture failure: {specialist}")
                    return implementation(specialist_input)

                return run

            try:
                runner = SpecialistRunner(
                    registry={name: wrap(name) for name in REGISTRY}
                )
                decision = CfoTurnDecision(
                    action="execute",
                    capability_requests=[
                        CapabilityRequest(capability_id=case.team_capability_id)
                    ],
                )
                runtime = build_finance_runtime(
                    decision_engine=_StaticDecisionEngine(decision),
                    specialist_runner=runner,
                    web_research_service=_fixture_web_research_service(),
                    knowledge_retriever=_NoMatchKnowledgeRetriever(),
                    llm_client=None,
                )
                response = await runtime.handle(
                    user_id="acceptance-user",
                    chat_history=[],
                    memory_context={},
                    **case.input.model_dump(),
                )
                if len(saved_records) != 1:
                    raise RuntimeError("runtime did not persist exactly one run record")
                results.append(
                    evaluate_composed_team_acceptance_case(
                        case,
                        response,
                        saved_records[0],
                        captured_inputs,
                    )
                )
            except Exception:
                results.append(None)
    observations = [
        _observation(case.case_id, result, tags=(case.team_capability_id,))
        for case, result in zip(cases, results, strict=True)
    ]
    if all(result is not None for result in results):
        build_composed_team_acceptance_report(results)  # type: ignore[arg-type]
    return observations


async def _run_specialist_execution() -> list[_Observation]:
    report = await run_specialist_execution_eval()
    return [_observation(result.case_id, result) for result in report.results]


async def _run_memory() -> list[_Observation]:
    report = await run_memory_eval()
    return [_observation(result.case_id, result, tags=(result.category,)) for result in report.results]


def _run_knowledge() -> list[_Observation]:
    cases = load_knowledge_retrieval_cases()
    report = run_knowledge_retrieval_eval(
        _FixtureKnowledgeRetriever(cases),
        cases,
    )
    return [_observation(result.case_id, result, tags=(result.category,)) for result in report.results]


def _run_investment() -> list[_Observation]:
    report = run_investment_research_eval()
    return [_observation(result.case_id, result) for result in report.results]


SUITE_ADAPTERS: tuple[EvalSuiteAdapter, ...] = (
    EvalSuiteAdapter(
        suite_id="cfo_runtime_acceptance",
        fixture_ref="app/evals/fixtures/cfo_runtime_acceptance/cases.json",
        severity="critical",
        run=_run_cfo_acceptance,
    ),
    EvalSuiteAdapter(
        suite_id="composed_team_acceptance",
        fixture_ref="app/evals/fixtures/composed_team_acceptance/cases.json",
        severity="critical",
        run=_run_composed_team_acceptance,
    ),
    EvalSuiteAdapter(
        suite_id="specialist_execution",
        fixture_ref="app/evals/fixtures/specialist_execution/cases.json",
        severity="major",
        run=_run_specialist_execution,
    ),
    EvalSuiteAdapter(
        suite_id="memory",
        fixture_ref="app/evals/fixtures/memory/cases.json",
        severity="major",
        run=_run_memory,
    ),
    EvalSuiteAdapter(
        suite_id="knowledge_retrieval",
        fixture_ref="app/evals/fixtures/knowledge_retrieval/cases.json",
        severity="major",
        run=_run_knowledge,
    ),
    EvalSuiteAdapter(
        suite_id="investment_research",
        fixture_ref="app/evals/fixtures/investment_research/cases.json",
        severity="major",
        run=_run_investment,
    ),
)


async def run_offline_suites(config_fingerprint: str) -> list[EvalSuiteReport]:
    reports: list[EvalSuiteReport] = []
    for adapter in SUITE_ADAPTERS:
        value = adapter.run()
        observations = await value if isawaitable(value) else value
        reports.append(_project_suite(adapter, observations, config_fingerprint))
    return reports


def _project_suite(
    adapter: EvalSuiteAdapter,
    observations: Sequence[_Observation],
    config_fingerprint: str,
) -> EvalSuiteReport:
    tasks: list[EvalTask] = []
    trials: list[EvalTrial] = []
    graders: list[EvalGraderResult] = []
    cases: list[EvalCaseResult] = []
    for observation in sorted(observations, key=lambda item: item.case_id):
        task_id = f"{adapter.suite_id}:{observation.case_id}"
        grader_id = f"{adapter.suite_id}.existing"
        status = "error" if observation.errored else "pass" if observation.passed else "fail"
        reason_code = (
            "domain_eval_error"
            if observation.errored
            else "existing_grader_passed"
            if observation.passed
            else "domain_assertion_failed"
        )
        detail = (
            "domain eval raised an exception"
            if observation.errored
            else "existing domain grader passed"
            if observation.passed
            else f"{observation.failure_count} domain assertion(s) failed"
        )
        tasks.append(
            EvalTask(
                task_id=task_id,
                suite_id=adapter.suite_id,
                fixture_ref=adapter.fixture_ref,
                expected_outcome="existing_grader_pass",
                grader_ids=[grader_id],
                severity=adapter.severity,
                tags=list(observation.tags),
                limits=OFFLINE_TRIAL_LIMITS,
            )
        )
        trials.append(
            EvalTrial(
                trial_id=f"{task_id}:trial-1",
                task_id=task_id,
                mode="offline",
                profile_name="offline-hermetic-v1",
                config_fingerprint=config_fingerprint,
                status=status,
            )
        )
        graders.append(
            EvalGraderResult(
                grader_id=grader_id,
                dimension="domain_correctness",
                target="outcome",
                status=status,
                severity=adapter.severity,
                reason_code=reason_code,
                detail=detail,
            )
        )
        cases.append(
            EvalCaseResult(
                suite_id=adapter.suite_id,
                case_id=observation.case_id,
                status=status,
                severity=adapter.severity,
                reason_codes=[] if status == "pass" else [reason_code],
                details=[] if status == "pass" else [detail],
            )
        )
    return EvalSuiteReport(
        suite_id=adapter.suite_id,
        total=len(cases),
        passed=sum(case.status == "pass" for case in cases),
        failed=sum(case.status == "fail" for case in cases),
        errors=sum(case.status == "error" for case in cases),
        skipped=sum(case.status == "skip" for case in cases),
        tasks=tasks,
        trials=trials,
        graders=graders,
        cases=cases,
    )


def _observation(
    case_id: str,
    result: Any | None,
    *,
    tags: tuple[str, ...] = (),
) -> _Observation:
    if result is None:
        return _Observation(case_id=case_id, passed=False, errored=True, tags=tags)
    failures = getattr(result, "failures", [])
    return _Observation(
        case_id=case_id,
        passed=bool(getattr(result, "passed", False)),
        failure_count=len(failures),
        tags=tags,
    )


def _query_key(case: KnowledgeRetrievalEvalCase) -> tuple[Any, ...]:
    return _knowledge_query_key(
        KnowledgeQuery(
            text=case.query,
            top_k=case.top_k,
            as_of=case.as_of,
            filters=case.filters,
        )
    )


def _knowledge_query_key(query: KnowledgeQuery) -> tuple[Any, ...]:
    filters = query.filters
    return (
        query.text,
        query.top_k,
        query.as_of.isoformat(),
        tuple(filters.jurisdictions),
        tuple(filters.languages),
        tuple(filters.source_types),
        tuple(filters.tags),
        filters.include_stale,
    )


def _document_allowed(document: Any, query: KnowledgeQuery) -> bool:
    filters = query.filters
    if filters.jurisdictions and document.jurisdiction.lower() not in filters.jurisdictions:
        return False
    if filters.languages and document.language.lower() not in filters.languages:
        return False
    if filters.source_types and document.source_type not in filters.source_types:
        return False
    if filters.tags and not set(filters.tags).issubset(document.tags):
        return False
    return filters.include_stale or document.freshness(as_of=query.as_of) == "current"
