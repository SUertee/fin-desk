from app.runtime.observability.trace_collector import TraceCollector
from app.models.runtime import (
    AgentHandoff,
    AgentOutputValidation,
    AgentRunUsage,
    AgentToolCall,
)


def test_trace_collector_records_runtime_and_policy():
    trace = TraceCollector.start_run(
        user_id="demo",
        entrypoint="chat",
        runtime_requested="openai",
    )
    trace.set_policy({"complexity": "moderate", "audit_required": True})
    trace.set_input_summary({"message_length": 12, "transaction_count": 2})
    trace.select_agents(["cfo", "expense_analyst", "cfo"])
    trace.set_tools_available(["get_finance_context"])
    trace.record_tool_call("get_finance_context", agent="cfo")
    trace.record_output_validation(
        {
            "agent": "cfo",
            "contract": "ChatResponse",
            "status": "passed",
        }
    )
    trace.set_model_name("gpt-test")
    trace.set_output_contract("ChatResponse")
    trace.set_audit_status("needs_review")
    trace.set_usage(
        {
            "request_count": 1,
            "model_response_count": 1,
            "input_tokens": 100,
            "cached_input_tokens": 0,
            "uncached_input_tokens": 0,
            "output_tokens": 25,
            "total_tokens": 125,
        }
    )
    trace.set_cost(
        {
            "status": "complete",
            "reporting_currency": "USD",
            "billing_totals": [{"amount": "0.001", "currency": "USD"}],
            "reporting_total": {"amount": "0.001", "currency": "USD"},
        }
    )
    trace.mark_runtime_used("openai")

    logged = trace.to_log_dict()

    assert logged["schema_version"] == "agent-run-record/v2"
    assert logged["user_id"] == "demo"
    assert logged["entrypoint"] == "chat"
    assert logged["runtime_requested"] == "openai"
    assert logged["runtime_used"] == "openai"
    assert logged["model_name"] == "gpt-test"
    assert logged["policy"]["complexity"] == "moderate"
    assert logged["input_summary"]["message_length"] == 12
    assert logged["selected_agents"] == ["cfo", "expense_analyst"]
    assert logged["tools_available"] == ["get_finance_context"]
    assert logged["tool_calls"][0]["name"] == "get_finance_context"
    assert logged["output_validations"] == [
        {
            "agent": "cfo",
            "contract": "ChatResponse",
            "status": "passed",
            "errors": [],
        }
    ]
    assert logged["output_contract"] == "ChatResponse"
    assert logged["audit_status"] == "needs_review"
    assert logged["usage"] == {
        "request_count": 1,
        "model_response_count": 1,
        "input_tokens": 100,
        "cached_input_tokens": 0,
        "uncached_input_tokens": 0,
        "output_tokens": 25,
        "total_tokens": 125,
    }
    assert logged["cost"]["status"] == "complete"
    assert logged["cost"]["reporting_total"] == {
        "amount": "0.001",
        "currency": "USD",
    }
    assert logged["latency_ms"] >= 0


def test_trace_collector_records_error_type():
    trace = TraceCollector.start_run(
        user_id="demo",
        entrypoint="chat",
        runtime_requested="openai",
    )
    trace.fail(RuntimeError("unavailable"))

    logged = trace.to_log_dict()

    assert logged["runtime_used"] is None
    assert logged["error_type"] == "RuntimeError"


def test_trace_collector_merges_observed_run_facts():
    trace = TraceCollector.start_run(
        user_id="demo",
        entrypoint="chat",
        runtime_requested="openai",
    )
    trace.record_tool_call("consult_expense_analyst", agent="cfo")
    trace.record_handoff(
        from_agent="cfo",
        to_agent="expense_analyst",
        status="planned",
        reason="runtime_policy_required_specialist",
    )

    trace.record_observations(
        tool_calls=[
            AgentToolCall(
                name="consult_expense_analyst",
                status="called",
                agent="Finance CFO",
                latency_ms=12.5,
            )
        ],
        handoffs=[
            AgentHandoff(
                from_agent="cfo",
                to_agent="expense_analyst",
                status="completed",
                reason="sdk_agent_tool_output",
            )
        ],
        output_validations=[
            AgentOutputValidation(
                agent="expense_analyst",
                contract="SpecialistAgentOutput",
                status="passed",
            )
        ],
        usage=AgentRunUsage(
            request_count=2,
            model_response_count=2,
            input_tokens=80,
            output_tokens=20,
            total_tokens=100,
        ),
    )

    logged = trace.to_log_dict()

    assert logged["tool_calls"] == [
        {
            "name": "consult_expense_analyst",
            "status": "called",
            "agent": "Finance CFO",
            "latency_ms": 12.5,
        }
    ]
    assert logged["handoffs"] == [
        {
            "from_agent": "cfo",
            "to_agent": "expense_analyst",
            "status": "completed",
            "reason": "sdk_agent_tool_output",
            "output": None,
        }
    ]
    assert logged["output_validations"] == [
        {
            "agent": "expense_analyst",
            "contract": "SpecialistAgentOutput",
            "status": "passed",
            "errors": [],
        }
    ]
    assert logged["usage"]["total_tokens"] == 100


def test_trace_collector_records_output_validation_failure():
    trace = TraceCollector.start_run(
        user_id="demo",
        entrypoint="chat",
        runtime_requested="openai",
    )

    trace.record_output_validation(
        {
            "agent": "cfo",
            "contract": "ChatResponse",
            "status": "failed",
            "errors": ["reply: Field required (missing)"],
        }
    )

    logged = trace.to_log_dict()

    assert logged["output_validations"] == [
        {
            "agent": "cfo",
            "contract": "ChatResponse",
            "status": "failed",
            "errors": ["reply: Field required (missing)"],
        }
    ]


def test_add_usage_accumulates_across_stages():
    trace = TraceCollector.start_run(
        user_id="demo", entrypoint="chat", runtime_requested="self_hosted"
    )

    trace.add_usage(
        AgentRunUsage(
            request_count=1, model_response_count=1,
            input_tokens=100, cached_input_tokens=60,
            uncached_input_tokens=40, output_tokens=20, total_tokens=120,
        )
    )
    trace.add_usage(
        {"request_count": 1, "model_response_count": 1,
         "input_tokens": 40, "output_tokens": 10, "total_tokens": 50}
    )

    assert trace.usage.request_count == 2
    assert trace.usage.model_response_count == 2
    assert trace.usage.input_tokens == 140
    assert trace.usage.cached_input_tokens == 60
    assert trace.usage.uncached_input_tokens == 40
    assert trace.usage.output_tokens == 30
    assert trace.usage.total_tokens == 170


def test_add_usage_tolerates_none_and_empty():
    trace = TraceCollector.start_run(
        user_id="demo", entrypoint="chat", runtime_requested="self_hosted"
    )

    trace.add_usage(None)
    trace.add_usage({})
    trace.add_usage(AgentRunUsage())

    assert trace.usage.total_tokens == 0
    assert trace.usage.request_count == 0


def test_set_usage_keeps_overwrite_semantics():
    trace = TraceCollector.start_run(
        user_id="demo", entrypoint="chat", runtime_requested="self_hosted"
    )

    trace.add_usage({"request_count": 1, "input_tokens": 100, "total_tokens": 100})
    trace.set_usage({"request_count": 1, "input_tokens": 5, "total_tokens": 5})

    # set_usage overwrites (legacy single-stage behavior), never adds.
    assert trace.usage.input_tokens == 5
    assert trace.usage.total_tokens == 5
