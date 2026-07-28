"""Bounded in-request scheduling for specialist handoffs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

from app.models.runtime import RuntimePolicyResult
from app.runtime.execution.handoff import HandoffRequest, HandoffResult
from app.runtime.execution.specialist_runner import SpecialistRunner


ScheduledTaskStatus = Literal["completed", "failed", "timed_out"]


@dataclass(frozen=True)
class ScheduledHandoff:
    task_id: str
    request: HandoffRequest
    depends_on: tuple[str, ...] = ()
    parallel_safe: bool = False


@dataclass(frozen=True)
class ScheduledHandoffResult:
    task: ScheduledHandoff
    result: HandoffResult
    status: ScheduledTaskStatus
    latency_ms: float

    def ledger_dump(self) -> dict[str, Any]:
        return {
            "task_id": self.task.task_id,
            "specialist": self.task.request.to_agent,
            "status": self.status,
            "depends_on": list(self.task.depends_on),
            "parallel_safe": self.task.parallel_safe,
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True)
class HandoffScheduleResult:
    results: tuple[ScheduledHandoffResult, ...]

    def ledger_dump(self) -> dict[str, Any]:
        return {
            "stage": "specialist_execution",
            "tasks": [item.ledger_dump() for item in self.results],
        }


class HandoffScheduler:
    """Run ready workers concurrently while preserving plan dependencies."""

    def __init__(
        self,
        runner: SpecialistRunner,
        *,
        max_concurrency: int = 3,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        self.runner = runner
        self.max_concurrency = max_concurrency

    async def execute(
        self,
        tasks: list[ScheduledHandoff],
        *,
        policy: RuntimePolicyResult,
        completed_dependencies: tuple[str, ...] = (),
    ) -> HandoffScheduleResult:
        task_ids = [task.task_id for task in tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Scheduled handoff task ids must be unique")

        pending = list(tasks)
        completed = set(completed_dependencies)
        results: dict[str, ScheduledHandoffResult] = {}
        semaphore = asyncio.Semaphore(self.max_concurrency)
        while pending:
            ready = [
                task
                for task in pending
                if set(task.depends_on).issubset(completed)
            ]
            if not ready:
                unresolved = ", ".join(task.task_id for task in pending)
                raise ValueError(
                    f"Unresolvable handoff dependencies: {unresolved}"
                )

            for batch in self._execution_batches(ready):
                batch_results = await asyncio.gather(
                    *[
                        self._run_task(
                            task,
                            policy=policy,
                            semaphore=semaphore,
                        )
                        for task in batch
                    ]
                )
                for item in batch_results:
                    results[item.task.task_id] = item
                    completed.add(item.task.task_id)
                    pending.remove(item.task)

        return HandoffScheduleResult(
            results=tuple(results[task_id] for task_id in task_ids)
        )

    @staticmethod
    def _execution_batches(
        ready: list[ScheduledHandoff],
    ) -> list[list[ScheduledHandoff]]:
        batches: list[list[ScheduledHandoff]] = []
        parallel_batch: list[ScheduledHandoff] = []
        for task in ready:
            if task.parallel_safe:
                parallel_batch.append(task)
                continue
            if parallel_batch:
                batches.append(parallel_batch)
                parallel_batch = []
            batches.append([task])
        if parallel_batch:
            batches.append(parallel_batch)
        return batches

    async def _run_task(
        self,
        task: ScheduledHandoff,
        *,
        policy: RuntimePolicyResult,
        semaphore: asyncio.Semaphore,
    ) -> ScheduledHandoffResult:
        started = perf_counter()
        timeout_seconds = task.request.budget.timeout_ms / 1000
        try:
            async with semaphore:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.runner.run,
                        task.request,
                        policy=policy,
                    ),
                    timeout=timeout_seconds,
                )
            status: ScheduledTaskStatus = (
                "completed" if result.status == "completed" else "failed"
            )
        except TimeoutError:
            status = "timed_out"
            result = HandoffResult(
                from_agent=task.request.from_agent,
                to_agent=task.request.to_agent,
                status="failed",
                error_message="Specialist execution timed out",
            )
        except Exception as exc:
            status = "failed"
            result = HandoffResult(
                from_agent=task.request.from_agent,
                to_agent=task.request.to_agent,
                status="failed",
                error_message=str(exc),
            )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return ScheduledHandoffResult(
            task=task,
            result=result,
            status=status,
            latency_ms=latency_ms,
        )
