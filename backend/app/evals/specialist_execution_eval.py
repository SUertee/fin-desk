"""Offline regression eval for dependency-aware specialist execution."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from threading import Lock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistExecutionBudget,
    SpecialistName,
)
from app.models.runtime import RuntimePolicyResult
from app.runtime.execution.handoff import HandoffRequest
from app.runtime.execution.handoff_scheduler import (
    HandoffScheduleResult,
    HandoffScheduler,
    ScheduledHandoff,
    ScheduledTaskStatus,
)
from app.runtime.execution.specialist_runner import SpecialistRunner


FIXTURE = (
    Path(__file__).with_name("fixtures")
    / "specialist_execution"
    / "cases.json"
)


class SpecialistExecutionWorker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=80)
    specialist: SpecialistName
    delay_ms: int = Field(default=0, ge=0, le=2000)
    timeout_ms: int = Field(default=1000, ge=100, le=5000)
    depends_on: list[str] = Field(default_factory=list)
    parallel_safe: bool = False


class SpecialistExecutionEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=3, max_length=100)
    max_concurrency: int = Field(default=3, ge=1, le=8)
    workers: list[SpecialistExecutionWorker] = Field(min_length=1, max_length=8)
    expected_statuses: dict[str, ScheduledTaskStatus]
    min_speedup: float | None = Field(default=None, gt=1)
    min_observed_concurrency: int | None = Field(default=None, ge=1)
    max_observed_concurrency: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_task_references(self) -> "SpecialistExecutionEvalCase":
        task_ids = [worker.task_id for worker in self.workers]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("worker task IDs must be unique")
        specialists = [worker.specialist for worker in self.workers]
        if len(specialists) != len(set(specialists)):
            raise ValueError("worker specialists must be unique per case")
        if set(self.expected_statuses) != set(task_ids):
            raise ValueError("expected statuses must cover every worker")
        unknown = {
            dependency
            for worker in self.workers
            for dependency in worker.depends_on
            if dependency not in task_ids
        }
        if unknown:
            raise ValueError(f"unknown worker dependencies: {sorted(unknown)}")
        return self


class SpecialistExecutionEvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    passed: bool
    statuses: dict[str, ScheduledTaskStatus]
    result_order: list[str]
    dependency_order_valid: bool
    observed_max_concurrency: int = Field(ge=0)
    parallel_latency_ms: float = Field(ge=0)
    sequential_latency_ms: float | None = Field(default=None, ge=0)
    speedup: float | None = Field(default=None, ge=0)
    failures: list[str] = Field(default_factory=list)


class SpecialistExecutionEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    results: list[SpecialistExecutionEvalResult]

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


class _ExecutionProbe:
    def __init__(self, workers: list[SpecialistExecutionWorker]) -> None:
        self.workers = {worker.specialist: worker for worker in workers}
        self.events: list[str] = []
        self.active = 0
        self.max_active = 0
        self._lock = Lock()

    def registry(self):
        return {
            specialist: self._implementation(worker)
            for specialist, worker in self.workers.items()
        }

    def _implementation(self, worker: SpecialistExecutionWorker):
        def run(_input):
            with self._lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                self.events.append(f"start:{worker.task_id}")
            try:
                time.sleep(worker.delay_ms / 1000)
                return SpecialistAgentOutput(
                    specialist=worker.specialist,
                    confidence=0.8,
                )
            finally:
                with self._lock:
                    self.events.append(f"end:{worker.task_id}")
                    self.active -= 1

        return run


def load_specialist_execution_cases(
    path: Path = FIXTURE,
) -> list[SpecialistExecutionEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        SpecialistExecutionEvalCase.model_validate(item)
        for item in payload["cases"]
    ]


async def _execute_case(
    case: SpecialistExecutionEvalCase,
    *,
    max_concurrency: int,
) -> tuple[HandoffScheduleResult, _ExecutionProbe, float]:
    probe = _ExecutionProbe(case.workers)
    scheduler = HandoffScheduler(
        SpecialistRunner(registry=probe.registry()),
        max_concurrency=max_concurrency,
    )
    tasks = [
        ScheduledHandoff(
            task_id=worker.task_id,
            request=HandoffRequest(
                from_agent="cfo",
                to_agent=worker.specialist,
                task=f"Evaluate {worker.task_id}",
                output_contract="SpecialistAgentOutput",
                budget=SpecialistExecutionBudget(
                    timeout_ms=worker.timeout_ms
                ),
            ),
            depends_on=tuple(worker.depends_on),
            parallel_safe=worker.parallel_safe,
        )
        for worker in case.workers
    ]
    started = time.perf_counter()
    result = await scheduler.execute(
        tasks,
        policy=RuntimePolicyResult(),
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return result, probe, elapsed_ms


async def evaluate_specialist_execution_case(
    case: SpecialistExecutionEvalCase,
) -> SpecialistExecutionEvalResult:
    failures: list[str] = []
    parallel, probe, parallel_latency_ms = await _execute_case(
        case,
        max_concurrency=case.max_concurrency,
    )
    statuses = {
        item.task.task_id: item.status for item in parallel.results
    }
    result_order = [item.task.task_id for item in parallel.results]
    expected_order = [worker.task_id for worker in case.workers]
    if statuses != case.expected_statuses:
        failures.append(
            f"statuses={statuses!r}, expected {case.expected_statuses!r}"
        )
    if result_order != expected_order:
        failures.append(
            f"result order={result_order!r}, expected {expected_order!r}"
        )

    dependency_order_valid = _dependencies_are_ordered(case, probe.events)
    if not dependency_order_valid:
        failures.append("a dependent worker started before its dependency ended")
    if (
        case.min_observed_concurrency is not None
        and probe.max_active < case.min_observed_concurrency
    ):
        failures.append(
            f"max concurrency={probe.max_active}, expected at least "
            f"{case.min_observed_concurrency}"
        )
    if (
        case.max_observed_concurrency is not None
        and probe.max_active > case.max_observed_concurrency
    ):
        failures.append(
            f"max concurrency={probe.max_active}, expected at most "
            f"{case.max_observed_concurrency}"
        )

    sequential_latency_ms: float | None = None
    speedup: float | None = None
    if case.min_speedup is not None:
        _, _, sequential_latency_ms = await _execute_case(
            case,
            max_concurrency=1,
        )
        speedup = round(
            sequential_latency_ms / max(parallel_latency_ms, 0.01),
            2,
        )
        if speedup < case.min_speedup:
            failures.append(
                f"speedup={speedup}, expected at least {case.min_speedup}"
            )

    return SpecialistExecutionEvalResult(
        case_id=case.case_id,
        passed=not failures,
        statuses=statuses,
        result_order=result_order,
        dependency_order_valid=dependency_order_valid,
        observed_max_concurrency=probe.max_active,
        parallel_latency_ms=parallel_latency_ms,
        sequential_latency_ms=sequential_latency_ms,
        speedup=speedup,
        failures=failures,
    )


def _dependencies_are_ordered(
    case: SpecialistExecutionEvalCase,
    events: list[str],
) -> bool:
    positions = {event: index for index, event in enumerate(events)}
    for worker in case.workers:
        for dependency in worker.depends_on:
            dependency_end = positions.get(f"end:{dependency}")
            worker_start = positions.get(f"start:{worker.task_id}")
            if (
                dependency_end is None
                or worker_start is None
                or dependency_end > worker_start
            ):
                return False
    return True


async def run_specialist_execution_eval(
    cases: list[SpecialistExecutionEvalCase] | None = None,
) -> SpecialistExecutionEvalReport:
    selected = cases if cases is not None else load_specialist_execution_cases()
    results = [
        await evaluate_specialist_execution_case(case)
        for case in selected
    ]
    return SpecialistExecutionEvalReport(
        total=len(results),
        passed=sum(result.passed for result in results),
        results=results,
    )


def format_report(report: SpecialistExecutionEvalReport) -> str:
    lines = [
        f"specialist execution eval: {report.passed}/{report.total} "
        f"({report.accuracy:.0%})"
    ]
    for result in report.results:
        timing = f"{result.parallel_latency_ms:.0f}ms"
        if result.speedup is not None:
            timing += f", {result.speedup:.2f}x"
        status: Literal["PASS", "FAIL"] = "PASS" if result.passed else "FAIL"
        lines.append(f"  {status} {result.case_id}: {timing}")
        for failure in result.failures:
            lines.append(f"    - {failure}")
    return "\n".join(lines)


if __name__ == "__main__":
    eval_report = asyncio.run(run_specialist_execution_eval())
    print(format_report(eval_report))
    raise SystemExit(0 if eval_report.passed == eval_report.total else 1)
