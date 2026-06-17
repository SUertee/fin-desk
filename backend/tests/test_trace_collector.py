from app.runtime.trace_collector import TraceCollector


def test_trace_collector_records_runtime_and_policy():
    trace = TraceCollector.start_run(user_id="demo", runtime_requested="openai")
    trace.set_policy({"complexity": "moderate", "audit_required": True})
    trace.set_tools_available(["get_finance_context"])
    trace.mark_runtime_used("openai")

    logged = trace.to_log_dict()

    assert logged["user_id"] == "demo"
    assert logged["runtime_requested"] == "openai"
    assert logged["runtime_used"] == "openai"
    assert logged["policy"]["complexity"] == "moderate"
    assert logged["tools_available"] == ["get_finance_context"]
    assert logged["latency_ms"] >= 0


def test_trace_collector_records_error_type():
    trace = TraceCollector.start_run(user_id="demo", runtime_requested="openai")
    trace.fail(RuntimeError("unavailable"))

    logged = trace.to_log_dict()

    assert logged["runtime_used"] is None
    assert logged["error_type"] == "RuntimeError"
