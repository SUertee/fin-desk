import time
from threading import Barrier

import pytest

from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistExecutionBudget,
)
from app.models.runtime import RuntimePolicyResult
from app.runtime.execution.handoff import HandoffRequest
from app.runtime.execution.handoff_scheduler import (
    HandoffScheduler,
    ScheduledHandoff,
)
from app.runtime.execution.specialist_runner import SpecialistRunner


def _request(
    specialist: str,
    *,
    timeout_ms: int = 1000,
) -> HandoffRequest:
    return HandoffRequest(
        from_agent="cfo",
        to_agent=specialist,
        task=f"Run {specialist}",
        output_contract="SpecialistAgentOutput",
        budget=SpecialistExecutionBudget(timeout_ms=timeout_ms),
    )


def _output(specialist: str) -> SpecialistAgentOutput:
    return SpecialistAgentOutput(
        specialist=specialist,
        confidence=0.8,
    )


@pytest.mark.asyncio
async def test_scheduler_runs_independent_parallel_safe_handoffs_concurrently():
    barrier = Barrier(2)

    def expense(_input):
        barrier.wait(timeout=1)
        return _output("expense_analyst")

    def budget(_input):
        barrier.wait(timeout=1)
        return _output("budget_coach")

    scheduler = HandoffScheduler(
        SpecialistRunner(
            registry={
                "expense_analyst": expense,
                "budget_coach": budget,
            }
        ),
        max_concurrency=2,
    )

    result = await scheduler.execute(
        [
            ScheduledHandoff(
                "finance.expense_review",
                _request("expense_analyst"),
                parallel_safe=True,
            ),
            ScheduledHandoff(
                "finance.budget_coaching",
                _request("budget_coach"),
                parallel_safe=True,
            ),
        ],
        policy=RuntimePolicyResult(),
    )

    assert [item.status for item in result.results] == [
        "completed",
        "completed",
    ]


@pytest.mark.asyncio
async def test_scheduler_waits_for_declared_dependency():
    events: list[str] = []

    def expense(_input):
        events.append("expense")
        return _output("expense_analyst")

    def budget(_input):
        events.append("budget")
        return _output("budget_coach")

    scheduler = HandoffScheduler(
        SpecialistRunner(
            registry={
                "expense_analyst": expense,
                "budget_coach": budget,
            }
        )
    )

    result = await scheduler.execute(
        [
            ScheduledHandoff(
                "expense",
                _request("expense_analyst"),
                parallel_safe=True,
            ),
            ScheduledHandoff(
                "budget",
                _request("budget_coach"),
                depends_on=("expense",),
                parallel_safe=True,
            ),
        ],
        policy=RuntimePolicyResult(),
    )

    assert events == ["expense", "budget"]
    assert [item.task.task_id for item in result.results] == [
        "expense",
        "budget",
    ]


@pytest.mark.asyncio
async def test_scheduler_preserves_partial_success_when_worker_times_out():
    def slow(_input):
        time.sleep(0.2)
        return _output("expense_analyst")

    scheduler = HandoffScheduler(
        SpecialistRunner(
            registry={
                "expense_analyst": slow,
                "budget_coach": lambda _input: _output("budget_coach"),
            }
        ),
        max_concurrency=2,
    )

    result = await scheduler.execute(
        [
            ScheduledHandoff(
                "slow",
                _request("expense_analyst", timeout_ms=100),
                parallel_safe=True,
            ),
            ScheduledHandoff(
                "fast",
                _request("budget_coach", timeout_ms=100),
                parallel_safe=True,
            ),
        ],
        policy=RuntimePolicyResult(),
    )

    assert [item.status for item in result.results] == [
        "timed_out",
        "completed",
    ]
    assert result.results[0].result.status == "failed"
    assert "timed out" in result.results[0].result.error_message


@pytest.mark.asyncio
async def test_scheduler_rejects_unresolvable_dependencies():
    scheduler = HandoffScheduler(SpecialistRunner())

    with pytest.raises(ValueError, match="Unresolvable handoff dependencies"):
        await scheduler.execute(
            [
                ScheduledHandoff(
                    "expense",
                    _request("expense_analyst"),
                    depends_on=("missing",),
                    parallel_safe=True,
                )
            ],
            policy=RuntimePolicyResult(),
        )


@pytest.mark.asyncio
async def test_scheduler_ledger_projection_is_bounded():
    scheduler = HandoffScheduler(SpecialistRunner())

    result = await scheduler.execute(
        [
            ScheduledHandoff(
                "expense",
                _request("expense_analyst"),
                parallel_safe=True,
            )
        ],
        policy=RuntimePolicyResult(),
    )

    projection = result.ledger_dump()
    assert projection["stage"] == "specialist_execution"
    assert set(projection["tasks"][0]) == {
        "task_id",
        "specialist",
        "status",
        "depends_on",
        "parallel_safe",
        "latency_ms",
    }
