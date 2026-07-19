"""Office sessions: routes, chat wiring, steps event, evidence projection."""

import json

import pytest

from app.models.chat import ChatRequest
from app.models.office import CreateSessionRequest, UpdateSessionRequest
from app.routes import chat as chat_route
from app.routes import office as office_route
from app.runtime.observability.steps_projection import project_steps
from app.services import memory as memory_service


@pytest.fixture(autouse=True)
def reset_memory_cache():
    memory_service._history.clear()
    memory_service._loaded_from_db.clear()
    yield


@pytest.fixture
def store(monkeypatch):
    """In-memory session + message store faked across office and chat routes."""

    state = {"sessions": {}, "messages": [], "counter": 0}

    def fake_create(user_id, *, title="", session_id=None):
        state["counter"] += 1
        sid = session_id or f"sess_{state['counter']}"
        session = {
            "id": sid, "user_id": user_id, "title": title, "status": "active",
            "last_message_preview": "", "created_at": "2026-07-07T00:00:00",
            "updated_at": "2026-07-07T00:00:00",
        }
        state["sessions"][sid] = session
        return dict(session)

    def fake_get(user_id, session_id):
        session = state["sessions"].get(session_id)
        return dict(session) if session and session["user_id"] == user_id else None

    def fake_list(user_id, *, include_archived=False, limit=50):
        rows = [
            dict(s) for s in state["sessions"].values()
            if s["user_id"] == user_id
            and (include_archived or s["status"] == "active")
        ]
        return rows

    def fake_update(user_id, session_id, *, title=None, status=None, last_message_preview=None):
        session = state["sessions"].get(session_id)
        if not session:
            return False
        if title is not None:
            session["title"] = title
        if status is not None:
            session["status"] = status
        if last_message_preview is not None:
            session["last_message_preview"] = last_message_preview[:60]
        return True

    def fake_save_db(user_id, role, content, session_id="", request_id=""):
        state["messages"].append({
            "user_id": user_id, "role": role, "content": content,
            "session_id": session_id, "request_id": request_id,
        })
        return True

    def fake_list_messages(user_id, session_id, limit=200):
        return [
            {"id": str(i), "role": m["role"], "content": m["content"],
             "request_id": m["request_id"] or None, "created_at": "2026-07-07T00:00:00"}
            for i, m in enumerate(state["messages"])
            if m["user_id"] == user_id and m["session_id"] == session_id
        ]

    for module in (office_route,):
        monkeypatch.setattr(module, "create_session_db", fake_create)
        monkeypatch.setattr(module, "get_session_db", fake_get)
        monkeypatch.setattr(module, "list_sessions_db", fake_list)
        monkeypatch.setattr(module, "update_session_db", fake_update)
        monkeypatch.setattr(module, "list_session_messages_db", fake_list_messages)
    monkeypatch.setattr(chat_route, "get_session_db", fake_get)
    monkeypatch.setattr(chat_route, "update_session_db", fake_update)
    monkeypatch.setattr(memory_service, "save_message_db", fake_save_db)
    monkeypatch.setattr(
        memory_service,
        "get_chat_history_db",
        lambda user_id, limit, session_id="": [],
    )
    return state


class TestSessionRoutes:
    def test_create_and_list(self, store):
        session = office_route.create_session(CreateSessionRequest(user_id="demo", title="月度检查"))

        assert session.title == "月度检查"
        listed = office_route.list_sessions("demo")
        assert len(listed["sessions"]) == 1

    def test_seed_messages_promote_floating_chat(self, store):
        session = office_route.create_session(
            CreateSessionRequest(
                user_id="demo",
                seed_messages=[
                    {"role": "user", "content": "6月10日为什么花这么多？"},
                    {"role": "assistant", "content": "当日支出主要来自购物。"},
                ],
            )
        )

        assert session.title == "6月10日为什么花这么多？"[:24]
        messages = office_route.list_messages("demo", session.id)["messages"]
        assert len(messages) == 2
        assert messages[0]["request_id"] is None  # promoted turns carry no run linkage

    def test_messages_include_safe_conversation_route(self, store, monkeypatch):
        session = office_route.create_session(CreateSessionRequest(user_id="demo", title="t"))
        store["messages"].append(
            {
                "user_id": "demo",
                "role": "assistant",
                "content": "shopping 本月支出 ¥11,348。",
                "session_id": session.id,
                "request_id": "req-1",
            }
        )
        monkeypatch.setattr(
            office_route,
            "get_agent_run_record_db",
            lambda rid: {
                "policy": {
                    "conversation_route": {
                        "intent": "finance_query",
                        "execution_path": "cfo_analysis",
                        "run_finance_pipeline": True,
                        "emit_steps": True,
                        "attach_evidence": True,
                        "memory_scope": "finance_context",
                        "response_mode": "analysis",
                        "label": "finance analysis",
                        "ui_hints": {
                            "show_process": True,
                            "show_evidence_chips": True,
                            "structured_answer": True,
                        },
                    }
                }
            },
        )

        messages = office_route.list_messages("demo", session.id)["messages"]

        assert messages[0]["route"]["execution_path"] == "cfo_analysis"
        assert messages[0]["route"]["attach_evidence"] is True

    def test_archive_excluded_from_default_list(self, store):
        session = office_route.create_session(CreateSessionRequest(user_id="demo", title="t"))
        office_route.update_session("demo", session.id, UpdateSessionRequest(status="archived"))

        assert office_route.list_sessions("demo")["sessions"] == []
        assert len(office_route.list_sessions("demo", include_archived=True)["sessions"]) == 1

    def test_unknown_session_messages_404(self, store):
        response = office_route.list_messages("demo", "sess_nope")

        assert response.status_code == 404


@pytest.mark.asyncio
class TestChatSessionWiring:
    async def test_chat_persists_into_session_with_request_id(self, store, monkeypatch):
        monkeypatch.setattr(chat_route, "list_transactions_db", lambda u, limit=2000: [
            {"amount": -10, "date": "2026-06-01", "month": "2026-06"}
        ])
        monkeypatch.setattr(chat_route, "get_latest_analysis_run_db", lambda u: None)
        session = office_route.create_session(CreateSessionRequest(user_id="demo"))

        result = await chat_route.chat(
            ChatRequest(user_id="demo", message="分析我的消费", session_id=session.id)
        )

        rows = [m for m in store["messages"] if m["session_id"] == session.id]
        assert [m["role"] for m in rows] == ["user", "assistant"]
        assert rows[1]["request_id"] == result.request_id
        # auto-title from first user message + preview refreshed
        assert store["sessions"][session.id]["title"] == "分析我的消费"
        assert store["sessions"][session.id]["last_message_preview"]

    async def test_unknown_session_rejected_before_run(self, store):
        response = await chat_route.chat(
            ChatRequest(user_id="demo", message="hi", session_id="sess_nope")
        )

        assert response.status_code == 404
        assert store["messages"] == []

    async def test_no_session_keeps_flat_history(self, store, monkeypatch):
        monkeypatch.setattr(chat_route, "list_transactions_db", lambda u, limit=2000: [])
        monkeypatch.setattr(chat_route, "get_latest_analysis_run_db", lambda u: None)

        await chat_route.chat(ChatRequest(user_id="demo", message="hello"))

        assert all(m["session_id"] == "" for m in store["messages"])
        assert store["sessions"] == {}


@pytest.mark.asyncio
class TestStepsEvent:
    async def test_stream_orders_steps_before_deltas(self, store, monkeypatch):
        monkeypatch.setattr(chat_route, "list_transactions_db", lambda u, limit=2000: [
            {"amount": -10, "date": "2026-06-01", "month": "2026-06"}
        ])
        monkeypatch.setattr(chat_route, "get_latest_analysis_run_db", lambda u: None)

        class FakeLLM:
            def available(self, profile="chat"):
                return True

            async def generate_text_stream(self, prompt, *, profile="chat", system="", on_delta=None):
                from app.models.runtime import AgentRunUsage
                from app.runtime.llm.client import LLMResponse

                for chunk in ("你", "好"):
                    await on_delta(chunk)
                return LLMResponse(content="你好", usage=AgentRunUsage(requests=1), model_name="deepseek-chat")

        monkeypatch.setattr(chat_route._runtime, "llm_client", FakeLLM())
        session = office_route.create_session(CreateSessionRequest(user_id="demo"))

        response = await chat_route.chat_stream(
            ChatRequest(user_id="demo", message="分析消费", session_id=session.id)
        )
        events = []
        async for frame in response.body_iterator:
            for line in frame.strip().split("\n\n"):
                if line.startswith("data:"):
                    events.append(json.loads(line[5:]))

        kinds = [e["type"] for e in events]
        assert kinds[0] == "steps"
        assert "delta" in kinds and kinds[-1] == "done"
        assert kinds.index("steps") < kinds.index("delta")
        steps = events[0]["steps"]
        assert all({"label", "kind", "done"} <= set(s) for s in steps)
        # user-level labels, no payloads or latency
        assert not any("latency" in s or "payload" in s for s in steps)


class TestStepsProjection:
    def test_labels_and_hidden_tools(self):
        record = {
            "tool_calls": [
                {"name": "get_finance_context", "status": "called"},
                {"name": "query_transactions", "status": "called"},
                {"name": "llm_compose", "status": "called"},
                {"name": "consult_auditor", "status": "called"},
            ],
            "handoffs": [
                {"to_agent": "expense_analyst", "status": "completed"},
                {"to_agent": "auditor", "status": "completed"},
            ],
        }

        steps = project_steps(record)

        labels = [s["label"] for s in steps]
        assert "读取财务上下文" in labels and "查询账本明细" in labels
        assert "Expense Analyst 分析" in labels and "审计复核" in labels
        assert not any("llm" in label or "consult" in label for label in labels)
        audit_step = next(s for s in steps if s["label"] == "审计复核")
        assert audit_step["kind"] == "audit"


FORBIDDEN_EVIDENCE_KEYS = {
    "latency", "latency_ms", "usage", "input_tokens", "output_tokens",
    "cost", "estimated_total_cost", "model_name", "provider",
    "confidence", "internal_score",
}


def _all_keys(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from _all_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _all_keys(item)


class TestEvidenceProjection:
    def _fake_run(self):
        # get_agent_run_record_db returns the record JSONB directly
        return {
            "request_id": "req-1",
            "user_id": "demo",
            "audit_status": "verified",
            "input_summary": {"transaction_count": 682},
            "tool_calls": [
                {"name": "get_finance_context", "status": "called", "latency_ms": 2.8},
                {"name": "query_transactions", "status": "called", "latency_ms": 4.1},
            ],
            "handoffs": [
                {
                    "to_agent": "expense_analyst",
                    "status": "completed",
                    "output": {
                        "specialist": "expense_analyst",
                        "confidence": 0.78,
                        "findings": [
                            {"title": "shopping 是最大的支出类目", "evidence": ["shopping 合计 11348"]}
                        ],
                    },
                }
            ],
        }

    def test_projection_contents(self, monkeypatch):
        monkeypatch.setattr(office_route, "get_agent_run_record_db", lambda rid: self._fake_run())
        monkeypatch.setattr(
            office_route, "list_latest_quality_reports_db",
            lambda u: [{"source_type": "alipay", "imported_count": 174, "warnings": ["w1"]}],
        )

        projection = office_route.get_evidence("req-1")

        assert projection.findings[0].agent == "expense_analyst"
        assert "账本：682 笔已加载交易" in projection.cited_sources
        assert projection.data_coverage.source_counts == {"alipay": 174}
        assert projection.audit.status == "verified"
        assert projection.advanced.run_id == "req-1"
        assert "query_transactions" in projection.advanced.tool_names

    def test_investment_source_requires_sourced_specialist_finding(self, monkeypatch):
        record = self._fake_run()
        record["tool_calls"].append(
            {"name": "get_investment_research_context", "status": "called"}
        )
        record["handoffs"] = [
            {
                "to_agent": "investment_research",
                "status": "completed",
                "output": {
                    "specialist": "investment_research",
                    "findings": [],
                },
            }
        ]
        monkeypatch.setattr(office_route, "get_agent_run_record_db", lambda rid: record)
        monkeypatch.setattr(office_route, "list_latest_quality_reports_db", lambda u: [])

        projection = office_route.get_evidence("req-1")

        assert "外部行情研究（来源与时间见团队发现）" not in projection.cited_sources

        record["handoffs"][0]["output"]["findings"] = [
            {
                "title": "AAPL latest quote is USD 210.50",
                "evidence": ["Source: openbb:yfinance; as of 2026-07-18"],
            }
        ]
        projection = office_route.get_evidence("req-1")
        assert "外部行情研究（来源与时间见团队发现）" in projection.cited_sources

    def test_forbidden_fields_absent(self, monkeypatch):
        monkeypatch.setattr(office_route, "get_agent_run_record_db", lambda rid: self._fake_run())
        monkeypatch.setattr(office_route, "list_latest_quality_reports_db", lambda u: [])

        payload = office_route.get_evidence("req-1").model_dump()

        leaked = FORBIDDEN_EVIDENCE_KEYS & set(_all_keys(payload))
        assert not leaked, f"developer-layer fields leaked into user evidence: {leaked}"

    def test_unknown_run_404(self, monkeypatch):
        monkeypatch.setattr(office_route, "get_agent_run_record_db", lambda rid: None)

        response = office_route.get_evidence("nope")

        assert response.status_code == 404


@pytest.mark.asyncio
class TestSessionMemoryIsolation:
    """Session memory (summary/topic) must be scoped to the CFO Room session,
    not shared through the "default" scope across rooms."""

    @pytest.fixture
    def memory_store(self, monkeypatch):
        from app.runtime.memory import session_context

        session_context.reset_in_process_memory_for_test()
        state: dict[tuple[str, str], dict] = {}
        monkeypatch.setattr(
            "app.runtime.memory.session_context.get_session_memory_db",
            lambda user_id, session_id="default": state.get((user_id, session_id)),
        )
        monkeypatch.setattr(
            "app.runtime.memory.session_context.save_session_memory_db",
            lambda user_id, memory, session_id="default": bool(
                state.__setitem__((user_id, session_id), dict(memory)) or True
            ),
        )
        # Deterministic replies only: keep the LLM composer out of the way.
        monkeypatch.setattr(chat_route._runtime, "llm_client", None)
        monkeypatch.setattr(chat_route, "list_transactions_db", lambda u, limit=2000: [
            {"amount": -10, "date": "2026-06-01", "month": "2026-06"}
        ])
        monkeypatch.setattr(chat_route, "get_latest_analysis_run_db", lambda u: None)
        yield state
        session_context.reset_in_process_memory_for_test()

    async def test_room_summaries_do_not_cross_sessions(self, store, memory_store):
        room_a = office_route.create_session(CreateSessionRequest(user_id="demo", title="购物复盘"))
        room_b = office_route.create_session(CreateSessionRequest(user_id="demo", title="餐饮复盘"))

        await chat_route.chat(
            ChatRequest(user_id="demo", message="分析我的购物支出", session_id=room_a.id)
        )
        await chat_route.chat(
            ChatRequest(user_id="demo", message="分析我的餐饮支出", session_id=room_b.id)
        )

        assert set(memory_store) == {("demo", room_a.id), ("demo", room_b.id)}
        assert "购物" in memory_store[("demo", room_a.id)]["conversation_summary"]
        assert "餐饮" in memory_store[("demo", room_b.id)]["conversation_summary"]
        # No cross-room pollution in either direction.
        assert "餐饮" not in memory_store[("demo", room_a.id)]["conversation_summary"]
        assert "购物" not in memory_store[("demo", room_b.id)]["conversation_summary"]

    async def test_flat_chat_memory_stays_in_default_scope(self, store, memory_store):
        await chat_route.chat(ChatRequest(user_id="demo", message="分析我的消费"))

        assert set(memory_store) == {("demo", "default")}
