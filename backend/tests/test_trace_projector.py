from app.models.runtime import AgentHandoff, AgentOutputValidation, AgentRunRecord, AgentToolCall
from app.runtime.observability.trace_projector import project_run_record


def test_project_run_record_splits_ui_sections():
    record = AgentRunRecord(
        request_id="req-1",
        entrypoint="chat",
        user_id="demo",
        runtime_requested="self_hosted",
        runtime_used="self_hosted",
        selected_agents=["cfo", "expense_analyst"],
        tool_calls=[
            AgentToolCall(name="get_finance_context", status="called", agent="cfo")
        ],
        handoffs=[
            AgentHandoff(
                from_agent="cfo",
                to_agent="expense_analyst",
                status="completed",
                reason="typed_internal_a2a",
            )
        ],
        output_validations=[
            AgentOutputValidation(
                agent="cfo",
                contract="ChatResponse",
                status="passed",
            )
        ],
        output_contract="ChatResponse",
        latency_ms=12.3,
    )

    projection = project_run_record(record)

    assert projection["summary"]["runtime_used"] == "self_hosted"
    assert projection["tools"][0]["name"] == "get_finance_context"
    assert projection["handoffs"][0]["to_agent"] == "expense_analyst"
    assert projection["validations"][0]["contract"] == "ChatResponse"
    assert [item["kind"] for item in projection["timeline"]] == [
        "agent_selected",
        "agent_selected",
        "tool_call",
        "handoff",
        "validation",
    ]
