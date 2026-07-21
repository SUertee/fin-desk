"""Deterministic multi-turn memory and contextualization evaluation."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.runtime.memory.memory_context import assemble_memory_context
from app.runtime.orchestration.intake import TurnContextualizer

MEMORY_FIXTURES = Path(__file__).with_name("fixtures") / "memory" / "cases.json"


class MemoryEvalExpectation(BaseModel):
    recent_contents: list[str] | None = None
    summary_used: bool | None = None
    usage_reason: str | None = None
    truncated: bool | None = None
    resolution_status: str | None = None
    rewrite_applied: bool | None = None
    effective_contains: list[str] = Field(default_factory=list)
    effective_excludes: list[str] = Field(default_factory=list)
    slot_values: dict[str, str] = Field(default_factory=dict)


class MemoryEvalCase(BaseModel):
    case_id: str
    category: str
    chat_history: list[dict[str, str]] = Field(default_factory=list)
    session_memory: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    today: date = date(2026, 7, 6)
    expected: MemoryEvalExpectation


class MemoryCaseResult(BaseModel):
    case_id: str
    category: str
    passed: bool
    failures: list[str] = Field(default_factory=list)


class CategoryScore(BaseModel):
    total: int = 0
    passed: int = 0

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


class MemoryEvalReport(BaseModel):
    total: int
    passed: int
    by_category: dict[str, CategoryScore]
    results: list[MemoryCaseResult]

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def failures(self) -> list[MemoryCaseResult]:
        return [result for result in self.results if not result.passed]


def load_memory_cases(path: Path = MEMORY_FIXTURES) -> list[MemoryEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [MemoryEvalCase.model_validate(item) for item in payload["cases"]]


async def evaluate_memory_case(case: MemoryEvalCase) -> MemoryCaseResult:
    failures: list[str] = []
    memory = assemble_memory_context(
        chat_history=case.chat_history,
        session_memory=case.session_memory or None,
    )
    expected = case.expected

    if expected.recent_contents is not None:
        actual = [turn["content"] for turn in memory.recent_turns]
        if actual != expected.recent_contents:
            failures.append(f"recent contents {actual!r}")
    for field_name in ("summary_used", "usage_reason", "truncated"):
        expected_value = getattr(expected, field_name)
        if expected_value is not None and getattr(memory, field_name) != expected_value:
            failures.append(
                f"{field_name}={getattr(memory, field_name)!r}, expected {expected_value!r}"
            )

    if case.message is not None:
        outcome = await TurnContextualizer().contextualize_with_trace(
            case.message,
            chat_history=list(memory.recent_turns),
            memory_context=memory.model_dump(),
            today=case.today,
        )
        turn = outcome.turn
        if (
            expected.resolution_status is not None
            and turn.resolution_status != expected.resolution_status
        ):
            failures.append(
                f"resolution_status={turn.resolution_status}, expected {expected.resolution_status}"
            )
        if (
            expected.rewrite_applied is not None
            and turn.rewrite_applied != expected.rewrite_applied
        ):
            failures.append(
                f"rewrite_applied={turn.rewrite_applied}, expected {expected.rewrite_applied}"
            )
        for fragment in expected.effective_contains:
            if fragment not in turn.effective_message:
                failures.append(f"effective message missing {fragment!r}")
        for fragment in expected.effective_excludes:
            if fragment in turn.effective_message:
                failures.append(f"effective message unexpectedly contains {fragment!r}")
        slots = {slot.slot_type: slot.value for slot in turn.resolved_slots}
        for slot_type, expected_value in expected.slot_values.items():
            if slots.get(slot_type) != expected_value:
                failures.append(
                    f"slot {slot_type}={slots.get(slot_type)!r}, expected {expected_value!r}"
                )

    return MemoryCaseResult(
        case_id=case.case_id,
        category=case.category,
        passed=not failures,
        failures=failures,
    )


async def run_memory_eval(
    cases: list[MemoryEvalCase] | None = None,
) -> MemoryEvalReport:
    selected = cases if cases is not None else load_memory_cases()
    results = [await evaluate_memory_case(case) for case in selected]
    by_category: dict[str, CategoryScore] = {}
    for result in results:
        score = by_category.setdefault(result.category, CategoryScore())
        score.total += 1
        score.passed += int(result.passed)
    return MemoryEvalReport(
        total=len(results),
        passed=sum(item.passed for item in results),
        by_category=by_category,
        results=results,
    )


def format_report(report: MemoryEvalReport) -> str:
    lines = [f"memory eval: {report.passed}/{report.total} ({report.accuracy:.0%})"]
    for category, score in sorted(report.by_category.items()):
        lines.append(
            f"  {category:22} {score.passed}/{score.total} ({score.accuracy:.0%})"
        )
    for result in report.failures():
        lines.append(f"  - {result.case_id}: {'; '.join(result.failures)}")
    return "\n".join(lines)


if __name__ == "__main__":
    eval_report = asyncio.run(run_memory_eval())
    print(format_report(eval_report))
    raise SystemExit(0 if eval_report.passed == eval_report.total else 1)
