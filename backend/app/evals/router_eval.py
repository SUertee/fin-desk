"""Entry-router eval: per-category accuracy over a fixed case set.

Measures whether messages route to acceptable execution paths. Run the
deterministic baseline offline (zero LLM); the same runner accepts any
async route function so the hybrid router can be scored on the identical
set for a before/after comparison.

CLI: python -m app.evals.router_eval
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from app.models.routing import ConversationRoute

ROUTER_FIXTURES = Path(__file__).with_name("fixtures") / "router" / "cases.json"

# A prior CFO answer, used for cases that require conversation context.
_CONTEXT_HISTORY = [
    {"role": "user", "content": "先看购物支出，占比多少？"},
    {"role": "assistant", "content": "shopping 本月支出 ¥11,348，占总支出 22.7%，建议复核大额消费。"},
]

# Proven finance context: referring-back intents key on session memory
# (written only by the finance pipeline), not on raw chat text.
_CONTEXT_MEMORY = {
    "session_memory": {
        "last_topic": {"capability": "spending_review", "focus": "shopping"},
        "last_result_brief": "shopping 本月支出 ¥11,348，占总支出 22.7%，建议复核大额消费。",
    }
}

RouteFn = Callable[
    [str, list[dict[str, Any]], dict[str, Any] | None],
    Awaitable[ConversationRoute],
]


class RouterEvalCase(BaseModel):
    case_id: str
    category: str
    message: str
    has_prior_context: bool = False
    acceptable_paths: list[str]
    expect_pipeline: bool


class RouterCaseResult(BaseModel):
    case_id: str
    category: str
    passed: bool
    actual_path: str
    actual_pipeline: bool
    failures: list[str] = Field(default_factory=list)


class CategoryScore(BaseModel):
    total: int
    passed: int

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


class RouterEvalReport(BaseModel):
    total: int
    passed: int
    by_category: dict[str, CategoryScore]
    results: list[RouterCaseResult]

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def failures(self) -> list[RouterCaseResult]:
        return [result for result in self.results if not result.passed]


def load_router_cases(path: Path = ROUTER_FIXTURES) -> list[RouterEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [RouterEvalCase.model_validate(case) for case in payload["cases"]]


def evaluate_case(route: ConversationRoute, case: RouterEvalCase) -> RouterCaseResult:
    failures: list[str] = []
    if route.execution_path not in case.acceptable_paths:
        failures.append(
            f"path {route.execution_path} not in {case.acceptable_paths}"
        )
    if route.run_finance_pipeline != case.expect_pipeline:
        failures.append(
            f"pipeline {route.run_finance_pipeline}, expected {case.expect_pipeline}"
        )
    return RouterCaseResult(
        case_id=case.case_id,
        category=case.category,
        passed=not failures,
        actual_path=route.execution_path,
        actual_pipeline=route.run_finance_pipeline,
        failures=failures,
    )


async def run_router_eval(
    route_fn: RouteFn,
    cases: list[RouterEvalCase] | None = None,
) -> RouterEvalReport:
    cases = cases if cases is not None else load_router_cases()
    results: list[RouterCaseResult] = []
    by_category: dict[str, CategoryScore] = {}
    for case in cases:
        history = _CONTEXT_HISTORY if case.has_prior_context else []
        memory = _CONTEXT_MEMORY if case.has_prior_context else None
        route = await route_fn(case.message, history, memory)
        result = evaluate_case(route, case)
        results.append(result)
        score = by_category.setdefault(case.category, CategoryScore(total=0, passed=0))
        score.total += 1
        score.passed += int(result.passed)
    return RouterEvalReport(
        total=len(results),
        passed=sum(result.passed for result in results),
        by_category=by_category,
        results=results,
    )


def deterministic_route_fn() -> RouteFn:
    """Current rule router wrapped in the async eval interface."""

    from app.runtime.orchestration.router import EntryRouter

    router = EntryRouter()

    async def route_fn(
        message: str,
        chat_history: list[dict[str, Any]],
        memory_context: dict[str, Any] | None = None,
    ) -> ConversationRoute:
        return router.route(
            message, chat_history=chat_history, memory_context=memory_context
        )

    return route_fn


def hybrid_route_fn() -> RouteFn:
    """Hybrid router (rules + model classifier + guard) for the same eval set.

    With no DEEPSEEK_API_KEY the classifier is unavailable and this scores
    identically to the deterministic baseline.
    """

    from app.runtime.llm.deepseek_client import DeepSeekTextClient
    from app.runtime.orchestration.router import EntryRouter
    from app.runtime.orchestration.router import ModelIntentClassifier

    client = DeepSeekTextClient()
    router = EntryRouter(classifier=ModelIntentClassifier(lambda: client))

    async def route_fn(
        message: str,
        chat_history: list[dict[str, Any]],
        memory_context: dict[str, Any] | None = None,
    ) -> ConversationRoute:
        decision = await router.decide(
            message, chat_history=chat_history, memory_context=memory_context
        )
        return decision.route

    return route_fn


def format_report(title: str, report: RouterEvalReport) -> str:
    lines = [
        f"== {title} ==",
        f"overall: {report.passed}/{report.total} ({report.accuracy:.0%})",
    ]
    for category, score in sorted(report.by_category.items()):
        lines.append(
            f"  {category:14} {score.passed}/{score.total} ({score.accuracy:.0%})"
        )
    misses = report.failures()
    if misses:
        lines.append("misses:")
        for result in misses:
            lines.append(
                f"  - {result.case_id}: -> {result.actual_path} ({'; '.join(result.failures)})"
            )
    return "\n".join(lines)


async def _main(hybrid: bool) -> None:
    report = await run_router_eval(deterministic_route_fn())
    print(format_report("deterministic baseline", report))
    if hybrid:
        from dotenv import load_dotenv

        load_dotenv()
        hybrid_report = await run_router_eval(hybrid_route_fn())
        print()
        print(format_report("hybrid (rules + classifier + guard)", hybrid_report))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Entry-router eval")
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="also score the hybrid router (requires DEEPSEEK_API_KEY)",
    )
    args = parser.parse_args()
    asyncio.run(_main(args.hybrid))
