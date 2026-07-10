from types import SimpleNamespace

import pytest

from app.models.runtime import AgentRunUsage, AgentToolCall
from app.runtime.observability.run_observer import (
    HarnessRunHooks,
    RunObservations,
    extract_run_observations,
    merge_run_observations,
)


def test_extract_run_observations_reads_tool_call_items_from_objects():
    result = SimpleNamespace(
        new_items=[
            SimpleNamespace(
                type="tool_call_item",
                agent=SimpleNamespace(name="Finance CFO"),
                raw_item=SimpleNamespace(name="consult_expense_analyst"),
            ),
            SimpleNamespace(
                type="tool_call_item",
                agent=SimpleNamespace(name="Finance CFO"),
                raw_item=SimpleNamespace(name="consult_expense_analyst"),
            ),
        ]
    )

    observations = extract_run_observations(result)

    assert len(observations.tool_calls) == 1
    assert observations.tool_calls[0].name == "consult_expense_analyst"
    assert observations.tool_calls[0].status == "called"
    assert observations.tool_calls[0].agent == "Finance CFO"


def test_extract_run_observations_validates_specialist_tool_output():
    result = SimpleNamespace(
        new_items=[
            SimpleNamespace(
                type="tool_call_item",
                agent=SimpleNamespace(name="Finance CFO"),
                raw_item=SimpleNamespace(
                    call_id="call-1",
                    name="consult_expense_analyst",
                ),
            ),
            SimpleNamespace(
                type="tool_call_output_item",
                raw_item=SimpleNamespace(
                    call_id="call-1",
                    output={
                        "specialist": "expense_analyst",
                        "confidence": 0.84,
                        "findings": [],
                        "recommendations": [],
                        "limitations": ["sample is small"],
                    },
                ),
            ),
        ]
    )

    observations = extract_run_observations(result)

    assert [
        validation.model_dump(mode="json")
        for validation in observations.output_validations
    ] == [
        {
            "agent": "expense_analyst",
            "contract": "SpecialistAgentOutput",
            "status": "passed",
            "errors": [],
        }
    ]


def test_extract_run_observations_records_specialist_output_validation_failure():
    result = {
        "new_items": [
            {
                "type": "tool_call_item",
                "raw_item": {
                    "call_id": "call-2",
                    "name": "consult_budget_coach",
                },
            },
            {
                "type": "tool_call_output_item",
                "raw_item": {
                    "call_id": "call-2",
                    "output": (
                        '{"specialist": "budget_coach", "confidence": 1.5, '
                        '"findings": [], "recommendations": [], "limitations": []}'
                    ),
                },
            },
        ]
    }

    observations = extract_run_observations(result)

    assert len(observations.output_validations) == 1
    validation = observations.output_validations[0]
    assert validation.agent == "budget_coach"
    assert validation.contract == "SpecialistAgentOutput"
    assert validation.status == "failed"
    assert "confidence:" in validation.errors[0]


def test_extract_run_observations_ignores_non_specialist_tool_output():
    result = {
        "new_items": [
            {
                "type": "tool_call_item",
                "raw_item": {
                    "call_id": "call-3",
                    "name": "get_finance_context",
                },
            },
            {
                "type": "tool_call_output_item",
                "raw_item": {
                    "call_id": "call-3",
                    "output": {"user_id": "demo"},
                },
            },
        ]
    }

    observations = extract_run_observations(result)

    assert observations.output_validations == []


def test_extract_run_observations_reads_handoff_items_from_dicts():
    result = {
        "new_items": [
            {
                "type": "handoff_call_item",
                "agent": {"name": "Finance CFO"},
                "raw_item": {"name": "transfer_to_finance_auditor"},
            },
            {
                "type": "handoff_output_item",
                "source_agent": {"name": "Finance CFO"},
                "target_agent": {"name": "Finance Auditor"},
            },
        ]
    }

    observations = extract_run_observations(result)

    assert observations.handoffs[0].from_agent == "Finance CFO"
    assert observations.handoffs[0].to_agent == "finance_auditor"
    assert observations.handoffs[0].status == "planned"
    assert observations.handoffs[1].from_agent == "Finance CFO"
    assert observations.handoffs[1].to_agent == "Finance Auditor"
    assert observations.handoffs[1].status == "completed"


def test_extract_run_observations_reads_usage_from_context_wrapper():
    result = SimpleNamespace(
        context_wrapper=SimpleNamespace(
            usage=SimpleNamespace(
                requests=2,
                input_tokens=120,
                output_tokens=45,
                total_tokens=165,
            )
        )
    )

    observations = extract_run_observations(result)

    assert observations.usage.request_count == 2
    assert observations.usage.model_response_count == 2
    assert observations.usage.input_tokens == 120
    assert observations.usage.output_tokens == 45
    assert observations.usage.total_tokens == 165


def test_extract_run_observations_reads_usage_from_raw_responses():
    result = {
        "raw_responses": [
            {"usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}},
            {"usage": {"prompt_tokens": 20, "completion_tokens": 7}},
        ]
    }

    observations = extract_run_observations(result)

    assert observations.usage.request_count == 2
    assert observations.usage.model_response_count == 2
    assert observations.usage.input_tokens == 30
    assert observations.usage.output_tokens == 12
    assert observations.usage.total_tokens == 42


def test_merge_run_observations_preserves_usage_and_hook_latency():
    result_observations = RunObservations(
        tool_calls=[
            AgentToolCall(
                name="consult_expense_analyst",
                status="called",
                agent="Finance CFO",
            )
        ],
        usage=AgentRunUsage(
            request_count=1,
            model_response_count=1,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        ),
    )
    hook_observations = RunObservations(
        tool_calls=[
            AgentToolCall(
                name="consult_expense_analyst",
                status="called",
                agent="Finance CFO",
                latency_ms=7.2,
            )
        ]
    )

    merged = merge_run_observations(result_observations, hook_observations)

    assert len(merged.tool_calls) == 1
    assert merged.tool_calls[0].latency_ms == 7.2
    assert merged.usage.total_tokens == 15


@pytest.mark.asyncio
async def test_harness_run_hooks_record_tool_timing_and_handoff():
    hooks = HarnessRunHooks()
    agent = SimpleNamespace(name="Finance CFO")
    tool = SimpleNamespace(name="consult_budget_coach")

    await hooks.on_tool_start(SimpleNamespace(tool_name="consult_budget_coach"), agent, tool)
    await hooks.on_tool_end(SimpleNamespace(tool_name="consult_budget_coach"), agent, tool, {})
    await hooks.on_handoff(None, agent, SimpleNamespace(name="Budget Coach"))

    assert hooks.observations.tool_calls[0].name == "consult_budget_coach"
    assert hooks.observations.tool_calls[0].status == "called"
    assert hooks.observations.tool_calls[0].latency_ms >= 0
    assert hooks.observations.handoffs[0].from_agent == "Finance CFO"
    assert hooks.observations.handoffs[0].to_agent == "Budget Coach"
    assert hooks.observations.handoffs[0].status == "completed"
