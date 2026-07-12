"""Contextualized turn intake: spec scenarios for contextualized-turn-intake.

Covers: complete queries, category/time substitution from last_query,
contextless references asking for clarification, evidence requests never
rewritten, model fallback safety, memory last_query read/write, and
runtime integration (tools read the effective message, history keeps raw).
"""

from datetime import date

import pytest

from app.runtime.orchestration.intake import (
    ModelTurnContextualizer,
    SlotResolver,
    TurnContextualizer,
)
from app.runtime.orchestration.router.facts import MessageFacts

TODAY = date(2026, 7, 6)

LAST_QUERY_SHOPPING_SHARE = {
    "session_memory": {
        "last_query": {
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "category": "shopping",
            "direction": "expense",
            "metric": "expense_share",
        },
        "last_topic": {"capability": "spending_review", "focus": "shopping"},
        "last_result_brief": "shopping 六月支出占比 22.7%。",
    }
}

LAST_QUERY_DINING_TOTAL = {
    "session_memory": {
        "last_query": {
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
            "category": "dining",
            "direction": "expense",
            "metric": "total",
        },
    }
}


def _resolve(message, memory=None, today=TODAY):
    facts = MessageFacts.from_message(message, [], memory)
    return SlotResolver().resolve(message, facts, memory, today=today)


class TestSlotResolver:
    def test_complete_query_is_not_rewritten(self):
        turn = _resolve("6月餐饮花了多少", LAST_QUERY_SHOPPING_SHARE)

        assert turn.resolution_status == "unchanged"
        assert turn.rewrite_applied is False
        assert turn.effective_message == "6月餐饮花了多少"
        slots = {slot.slot_type: slot for slot in turn.resolved_slots}
        assert slots["category"].value == "dining"
        assert slots["category"].source == "raw_message"
        assert slots["date_range"].value == "2026-06-01..2026-06-30"

    def test_category_substitution_reuses_range_and_metric(self):
        turn = _resolve("那餐饮呢？", LAST_QUERY_SHOPPING_SHARE)

        assert turn.resolution_status == "resolved"
        assert turn.rewrite_applied is True
        assert "2026年6月" in turn.effective_message
        assert "餐饮" in turn.effective_message
        assert "占比" in turn.effective_message
        slots = {slot.slot_type: slot for slot in turn.resolved_slots}
        assert slots["category"].value == "dining"
        assert slots["category"].source == "raw_message"
        assert slots["date_range"].value == "2026-06-01..2026-06-30"
        assert slots["date_range"].source == "last_query"
        for slot in turn.resolved_slots:
            assert slot.slot_type and slot.value and slot.source
            assert 0.0 <= slot.confidence <= 1.0

    def test_time_substitution_reuses_category_and_metric(self):
        turn = _resolve("那上个月呢？", LAST_QUERY_DINING_TOTAL)

        assert turn.resolution_status == "resolved"
        assert turn.rewrite_applied is True
        assert "2026年6月" in turn.effective_message  # last month vs TODAY
        assert "餐饮" in turn.effective_message
        assert "花了多少" in turn.effective_message
        slots = {slot.slot_type: slot for slot in turn.resolved_slots}
        assert slots["date_range"].value == "2026-06-01..2026-06-30"
        assert slots["date_range"].source == "raw_message"
        assert slots["category"].value == "dining"
        assert slots["category"].source == "last_query"

    def test_contextless_category_reference_asks_for_clarification(self):
        turn = _resolve("那餐饮呢？", memory=None)

        assert turn.resolution_status == "needs_clarification"
        assert turn.effective_message == "那餐饮呢？"
        assert turn.rewrite_applied is False
        assert all(slot.slot_type != "date_range" for slot in turn.resolved_slots)

    def test_contextless_day_reference_asks_for_clarification(self):
        turn = _resolve("这一天为什么花这么多？", memory=None)

        assert turn.resolution_status == "needs_clarification"
        assert turn.effective_message == "这一天为什么花这么多？"
        assert not turn.resolved_slots

    def test_day_reference_resolves_from_trusted_single_day(self):
        memory = {
            "session_memory": {
                "last_query": {"date_from": "2026-06-10", "date_to": "2026-06-10"}
            }
        }
        turn = _resolve("这一天为什么花这么多？", memory)

        assert turn.resolution_status == "resolved"
        assert "2026-06-10" in turn.effective_message
        assert turn.resolved_slots[0].slot_type == "date"
        assert turn.resolved_slots[0].source == "session_memory"

    def test_evidence_request_is_never_rewritten_into_a_query(self):
        turn = _resolve("为什么这样建议？", LAST_QUERY_SHOPPING_SHARE)

        assert turn.resolution_status == "unchanged"
        assert turn.rewrite_applied is False
        assert turn.effective_message == "为什么这样建议？"
        # traceability slots only — never synthesized category/date queries
        assert all(
            slot.slot_type not in ("category", "date_range")
            for slot in turn.resolved_slots
        )

    def test_long_sentence_with_ne_particle_is_not_rewritten(self):
        turn = _resolve("我最近餐饮开销有点大，有什么建议呢", LAST_QUERY_SHOPPING_SHARE)

        assert turn.rewrite_applied is False
        assert turn.effective_message == "我最近餐饮开销有点大，有什么建议呢"


class TestTurnContextualizerFacade:
    @pytest.mark.asyncio
    async def test_social_turns_are_never_rewritten(self):
        class ExplodingModel:
            def available(self):
                return True

            async def contextualize(self, *args, **kwargs):
                raise AssertionError("model must not be called for social turns")

        contextualizer = TurnContextualizer(model=ExplodingModel())
        turn = await contextualizer.contextualize(
            "哈哈", memory_context=LAST_QUERY_SHOPPING_SHARE
        )

        assert turn.resolution_status == "unchanged"
        assert turn.effective_message == "哈哈"

    @pytest.mark.asyncio
    async def test_model_failure_falls_back_to_deterministic(self):
        class FailingModel:
            def available(self):
                return True

            async def contextualize(self, *args, **kwargs):
                return None

        contextualizer = TurnContextualizer(model=FailingModel())
        turn = await contextualizer.contextualize("那餐饮呢？", memory_context=None)

        assert turn.resolution_status == "needs_clarification"
        assert turn.effective_message == "那餐饮呢？"

    @pytest.mark.asyncio
    async def test_model_used_only_for_unresolved_references(self):
        calls = []

        class RecordingModel:
            def available(self):
                return True

            async def contextualize(self, raw, chat_history=None, memory_context=None):
                calls.append(raw)
                return None

        contextualizer = TurnContextualizer(model=RecordingModel())
        await contextualizer.contextualize("那餐饮呢？", memory_context=LAST_QUERY_SHOPPING_SHARE)
        assert calls == []  # deterministic resolved it

        await contextualizer.contextualize("那个呢？", memory_context=None)
        assert calls == ["那个呢？"]  # ambiguous remainder only


class TestModelTurnContextualizer:
    @pytest.mark.asyncio
    async def test_execution_fields_in_model_output_cannot_influence_turn(self):
        from types import SimpleNamespace

        class FakeLLM:
            def __init__(self, data):
                self.data = data

            def available(self, profile="router"):
                return True

            async def generate_json(self, prompt, *, profile="router", system=""):
                return SimpleNamespace(data=self.data)

        model = ModelTurnContextualizer(
            lambda: FakeLLM(
                {
                    "effective_message": "2026年6月餐饮花了多少？",
                    "resolution_status": "resolved",
                    "resolved_slots": [
                        {"slot_type": "category", "value": "dining", "confidence": 0.9}
                    ],
                    "confidence": 0.9,
                    # hostile extras must be ignored
                    "execution_path": "cfo_analysis",
                    "tool": "run_sql",
                    "sql": "DROP TABLE transactions",
                }
            )
        )
        turn = await model.contextualize("那餐饮呢？")

        assert turn is not None
        assert turn.resolution_status == "resolved"
        assert turn.resolved_slots[0].source == "model"
        dumped = turn.model_dump()
        assert "execution_path" not in dumped
        assert "sql" not in dumped

        bad = ModelTurnContextualizer(
            lambda: FakeLLM({"resolution_status": "run_pipeline"})
        )
        assert await bad.contextualize("那餐饮呢？") is None


class TestLastQueryMemory:
    def test_write_and_preserve_last_query(self, monkeypatch):
        from app.runtime.memory import session_context

        session_context.reset_in_process_memory_for_test()
        monkeypatch.setattr(
            "app.runtime.memory.session_context.get_session_memory_db",
            lambda *args: None,
        )
        monkeypatch.setattr(
            "app.runtime.memory.session_context.save_session_memory_db",
            lambda user_id, memory, session_id="default": True,
        )

        session_context.write_session_context(
            user_id="demo",
            session_id="room-a",
            last_query={"category": "shopping", "date_from": "2026-06-01"},
        )
        # A later run with no typed query must not erase the useful query.
        session_context.write_session_context(
            user_id="demo", session_id="room-a", last_query=None, last_result_brief="x"
        )

        memory = session_context.read_session_context("demo", "room-a")
        assert memory["last_query"]["category"] == "shopping"

    def test_extractor_prefers_typed_query_filters(self):
        from app.runtime.memory.finance_memory_extractor import extract_finance_memory

        memory = extract_finance_memory(
            user_message="6月购物支出占比多少",
            response_payload={"reply": "ok", "data": {}},
            finance_context={
                "transaction_query": {
                    "filters": {
                        "date_from": "2026-06-01",
                        "date_to": "2026-06-30",
                        "category": "shopping",
                        "direction": "expense",
                    }
                }
            },
            chat_history=[],
        )

        assert memory["last_query"]["category"] == "shopping"
        assert memory["last_query"]["metric"] == "expense_share"

        no_query = extract_finance_memory(
            user_message="分析我的消费",
            response_payload={"reply": "ok", "data": {}},
            finance_context={},
            chat_history=[],
        )
        assert no_query["last_query"] is None


@pytest.mark.asyncio
class TestRuntimeIntegration:
    async def _run(self, monkeypatch, message, memory_context):
        from app.runtime.orchestration import finance_runtime as fr

        records = []
        monkeypatch.setattr(
            fr, "save_agent_run_record_db", lambda record: records.append(record) or True
        )
        captured_filters = []

        def fake_query(user_id, filters):
            captured_filters.append(filters)
            return {"filters": filters.model_dump(exclude_none=True), "total": 1234.5, "count": 7, "groups": []}

        monkeypatch.setattr(fr, "run_transaction_query", fake_query)
        runtime = fr.FinanceRuntime()
        runtime.llm_client = None  # zero LLM: deterministic intake + routing

        result = await runtime.handle(
            user_id="demo",
            message=message,
            profile={"name": "Demo", "monthly_income": 5000},
            transactions=[{"amount": -100, "category": "dining", "date": "2026-06-03"}],
            monthly_totals=[{"month": "2026-06", "net": 100}],
            chat_history=[{"role": "assistant", "content": "上一轮结论"}],
            memory_context=memory_context,
        )
        return result, records, captured_filters

    async def test_tools_read_effective_message_history_keeps_raw(self, monkeypatch):
        memory = {
            "session_memory": {
                "last_query": {
                    "date_from": "2026-06-01",
                    "date_to": "2026-06-30",
                    "category": "shopping",
                    "direction": "expense",
                    "metric": "total",
                },
                "last_topic": {"capability": "spending_review", "focus": "shopping"},
            }
        }
        result, records, captured = await self._run(monkeypatch, "那餐饮呢？", memory)

        # Typed query executed against the REWRITTEN message.
        assert captured, "query_transactions should run on the effective message"
        assert captured[0].category == "dining"
        assert captured[0].date_from == "2026-06-01"
        assert captured[0].date_to == "2026-06-30"
        # Run ledger records the rewrite for developers only.
        record = records[0]
        contextualization = record.policy["contextualization"]
        assert contextualization["rewrite_applied"] is True
        assert contextualization["resolution_status"] == "resolved"
        assert result["route"]["execution_path"] == "cfo_analysis"

    async def test_unresolved_reference_routes_to_clarification(self, monkeypatch):
        result, records, captured = await self._run(monkeypatch, "那餐饮呢？", None)

        assert captured == []  # no fabricated ledger query
        assert result["route"]["execution_path"] == "clarification"
        contextualization = records[0].policy["contextualization"]
        assert contextualization["resolution_status"] == "needs_clarification"

    async def test_chat_route_persists_raw_message(self, monkeypatch):
        from app.models.chat import ChatRequest
        from app.routes import chat as chat_route
        from app.services import memory as memory_service
        from app.runtime.orchestration import finance_runtime as fr

        memory_service._history.clear()
        memory_service._loaded_from_db.clear()
        saved = []
        monkeypatch.setattr(
            memory_service,
            "save_message_db",
            lambda user_id, role, content, session_id="", request_id="": saved.append(
                {"role": role, "content": content}
            )
            or True,
        )
        monkeypatch.setattr(
            memory_service, "get_chat_history_db", lambda u, l, session_id="": []
        )
        monkeypatch.setattr(
            "app.runtime.memory.session_context.get_session_memory_db",
            lambda user_id, session_id="default": {
                "last_query": {
                    "date_from": "2026-06-01",
                    "date_to": "2026-06-30",
                    "category": "shopping",
                    "direction": "expense",
                    "metric": "total",
                }
            },
        )
        monkeypatch.setattr(
            "app.runtime.memory.session_context.save_session_memory_db",
            lambda user_id, memory, session_id="default": True,
        )
        monkeypatch.setattr(fr, "save_agent_run_record_db", lambda record: True)
        monkeypatch.setattr(
            chat_route, "list_transactions_db", lambda u, limit=2000: [
                {"amount": -50, "category": "dining", "date": "2026-06-05"}
            ]
        )
        monkeypatch.setattr(chat_route, "get_latest_analysis_run_db", lambda u: None)
        monkeypatch.setattr(chat_route._runtime, "llm_client", None)

        await chat_route.chat(ChatRequest(user_id="demo", message="那餐饮呢？"))

        user_rows = [row for row in saved if row["role"] == "user"]
        assert user_rows and user_rows[0]["content"] == "那餐饮呢？"
