"""Contextualized turn intake: spec scenarios for contextualized-turn-intake.

Covers: complete queries, category/time substitution from last_query,
contextless references asking for clarification, evidence requests never
rewritten, model fallback safety, memory last_query read/write, and
runtime integration (tools read the effective message, history keeps raw).
"""

from datetime import date

import pytest

from app.runtime.orchestration.intake import (
    ModelContextualizationResult,
    ModelTurnContextualizer,
    SlotResolver,
    TurnContextualizer,
)
from tests.cfo_decision_fakes import clarify, direct, execute

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
    return SlotResolver().resolve(message, memory, today=today)


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
                return ModelContextualizationResult(status="failed")

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
                return ModelContextualizationResult(status="failed")

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
                    "ui_mode": "analysis",
                    "tool": "run_sql",
                    "sql": "DROP TABLE transactions",
                }
            )
        )
        result = await model.contextualize("那餐饮呢？")

        assert result.status == "called"
        turn = result.turn
        assert turn is not None
        assert turn.resolution_status == "resolved"
        assert turn.resolved_slots[0].source == "model"
        dumped = turn.model_dump()
        assert "ui_mode" not in dumped
        assert "sql" not in dumped

        # Invalid status enum -> output rejected, never a crash.
        bad = ModelTurnContextualizer(
            lambda: FakeLLM({"resolution_status": "run_pipeline"})
        )
        assert (await bad.contextualize("那餐饮呢？")).status == "invalid_output"

        # Contract-violating slot enums -> invalid_output as well.
        bad_slots = ModelTurnContextualizer(
            lambda: FakeLLM(
                {
                    "effective_message": "x",
                    "resolution_status": "resolved",
                    "resolved_slots": [{"slot_type": "sql_table", "value": "t"}],
                }
            )
        )
        assert (await bad_slots.contextualize("那餐饮呢？")).status == "invalid_output"

        # Provider errors -> failed.
        class ExplodingLLM:
            def available(self, profile="router"):
                return True

            async def generate_json(self, prompt, *, profile="router", system=""):
                raise TimeoutError("provider timeout")

        failing = ModelTurnContextualizer(lambda: ExplodingLLM())
        assert (await failing.contextualize("那餐饮呢？")).status == "failed"


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
    async def _run(self, monkeypatch, message, memory_context, decision_engine):
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
        runtime = fr.FinanceRuntime(decision_engine=decision_engine)
        runtime.llm_client = None

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
        result, records, captured = await self._run(
            monkeypatch,
            "那餐饮呢？",
            memory,
            execute("finance.query_transactions"),
        )

        # Typed query executed against the REWRITTEN message.
        assert captured, "query_transactions should run on the effective message"
        assert captured[0].category == "dining"
        assert captured[0].date_from == "2026-06-01"
        assert captured[0].date_to == "2026-06-30"
        # Run ledger records the rewrite for developers only.
        record = records[0]
        contextualization = record.policy["contextualization"]
        assert contextualization["stage"] == "turn_contextualization"
        assert contextualization["rewrite_applied"] is True
        assert contextualization["resolution_status"] == "resolved"
        assert contextualization["raw_message_excerpt"] == "那餐饮呢？"
        assert "2026年6月" in contextualization["effective_message_excerpt"]
        # Deterministic resolve: no fabricated LLM call anywhere.
        assert contextualization["model"]["status"] == "skipped_deterministic"
        assert "turn_contextualize" not in {c.name for c in record.tool_calls}
        # Bounded projection only — no history, no prompts, no payloads.
        assert set(contextualization) == {
            "stage",
            "raw_message_excerpt",
            "effective_message_excerpt",
            "resolution_status",
            "rewrite_applied",
            "confidence",
            "ambiguity_reason",
            "resolved_slots",
            "model",
        }
        assert result["execution"]["outcome"] == "executed"

    async def test_unresolved_reference_routes_to_clarification(self, monkeypatch):
        result, records, captured = await self._run(
            monkeypatch,
            "那餐饮呢？",
            None,
            clarify("请补充要查询的月份。"),
        )

        assert captured == []  # no fabricated ledger query
        assert result["execution"]["outcome"] == "clarification"
        contextualization = records[0].policy["contextualization"]
        assert contextualization["resolution_status"] == "needs_clarification"
        # llm_client is None -> the model stage is honestly "unavailable".
        assert contextualization["model"]["status"] == "skipped_model_unavailable"
        assert contextualization["effective_message_excerpt"] == ""

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
        monkeypatch.setattr(
            chat_route._runtime,
            "decision_engine",
            execute("finance.query_transactions"),
        )

        await chat_route.chat(ChatRequest(user_id="demo", message="那餐饮呢？"))

        user_rows = [row for row in saved if row["role"] == "user"]
        assert user_rows and user_rows[0]["content"] == "那餐饮呢？"


    async def test_capability_question_stays_light_end_to_end(self, monkeypatch):
        result, records, captured = await self._run(
            monkeypatch,
            "你有什么用？",
            None,
            direct("我可以分析账本、预算和投资研究证据。"),
        )

        execution = result["execution"]
        assert execution["outcome"] == "direct_response"
        assert execution["evidence_available"] is False
        assert execution["specialist_findings_available"] is False
        assert execution["process_available"] is False
        assert result["data"] is None  # no evidence / team-process payload
        assert captured == []


class TestIntakeOutcomeStatuses:
    @pytest.mark.asyncio
    async def test_deterministic_resolution_never_reports_a_model_call(self):
        contextualizer = TurnContextualizer(model=None)
        outcome = await contextualizer.contextualize_with_trace(
            "那餐饮呢？", memory_context=LAST_QUERY_SHOPPING_SHARE, today=TODAY
        )

        assert outcome.model_status == "skipped_deterministic"
        assert outcome.model_latency_ms is None
        assert outcome.turn.resolution_status == "resolved"

    @pytest.mark.asyncio
    async def test_unavailable_model_is_reported_as_skipped(self):
        class UnavailableModel:
            def available(self):
                return False

            async def contextualize(self, *args, **kwargs):
                raise AssertionError("must not be called")

        contextualizer = TurnContextualizer(model=UnavailableModel())
        outcome = await contextualizer.contextualize_with_trace(
            "那餐饮呢？", memory_context=None
        )

        assert outcome.model_status == "skipped_model_unavailable"
        assert outcome.turn.resolution_status == "needs_clarification"

    @pytest.mark.asyncio
    async def test_model_statuses_flow_through_the_facade(self):
        from app.runtime.orchestration.intake import (
            ContextualizedTurn,
            ModelContextualizationResult,
        )

        class TypedModel:
            def __init__(self, result):
                self.result = result

            def available(self):
                return True

            async def contextualize(self, *args, **kwargs):
                return self.result

        resolved = ModelContextualizationResult(
            status="called",
            turn=ContextualizedTurn(
                raw_message="那个呢？",
                effective_message="2026年6月餐饮花了多少？",
                rewrite_applied=True,
                resolution_status="resolved",
                confidence=0.8,
            ),
            model_name="deepseek-chat",
        )
        outcome = await TurnContextualizer(model=TypedModel(resolved)).contextualize_with_trace(
            "那个呢？", memory_context=None
        )
        assert outcome.model_status == "called"
        assert outcome.model_name == "deepseek-chat"
        assert outcome.model_latency_ms is not None
        assert outcome.turn.rewrite_applied is True

        for status in ("invalid_output", "failed"):
            outcome = await TurnContextualizer(
                model=TypedModel(ModelContextualizationResult(status=status))
            ).contextualize_with_trace("那个呢？", memory_context=None)
            assert outcome.model_status == status
            # deterministic turn stands; request never fails
            assert outcome.turn.resolution_status == "needs_clarification"


def test_turn_contextualize_hidden_from_user_steps():
    from app.runtime.observability.steps_projection import project_steps

    steps = project_steps(
        {
            "tool_calls": [{"name": "turn_contextualize", "status": "called"}],
            "handoffs": [],
        }
    )

    assert steps == []
