from app.runtime.orchestration.entry_router import EntryRouter


def test_router_keeps_acknowledgement_lightweight():
    route = EntryRouter().route("哈哈", chat_history=[{"role": "assistant", "content": "之前的分析"}])

    assert route.intent == "acknowledgement"
    assert route.execution_path == "light_reply"
    assert route.run_finance_pipeline is False
    assert route.emit_steps is False
    assert route.attach_evidence is False


def test_router_treats_short_typo_like_greeting_as_light_reply():
    route = EntryRouter().route("你哈珀", chat_history=[])

    assert route.intent == "small_talk"
    assert route.execution_path == "light_reply"
    assert route.run_finance_pipeline is False


def test_router_routes_finance_question_to_cfo_analysis():
    route = EntryRouter().route("这个月购物支出占比多少？", chat_history=[])

    assert route.intent == "finance_query"
    assert route.execution_path == "cfo_analysis"
    assert route.run_finance_pipeline is True
    assert route.emit_steps is True
    assert route.attach_evidence is True


def test_router_routes_contextual_followup_to_cfo_followup():
    route = EntryRouter().route(
        "继续展开 6 月 10 日",
        chat_history=[{"role": "assistant", "content": "6 月 10 日有一笔大额消费"}],
    )

    assert route.intent == "follow_up"
    assert route.execution_path == "cfo_followup"
    assert route.run_finance_pipeline is True


def test_router_routes_evidence_request_without_rerun():
    route = EntryRouter().route(
        "为什么这样建议？",
        chat_history=[{"role": "assistant", "content": "建议复核 shopping 支出"}],
    )

    assert route.intent == "evidence_request"
    assert route.execution_path == "evidence_only"
    assert route.run_finance_pipeline is False
    assert route.emit_steps is False
    assert route.attach_evidence is True


def test_router_asks_clarification_for_non_finance_question():
    route = EntryRouter().route("你能帮我写一段前端代码吗？", chat_history=[])

    assert route.intent == "clarification"
    assert route.execution_path == "clarification"
    assert route.run_finance_pipeline is False


# --- Regression: substring matching must not eat real requests ---


def test_router_does_not_treat_help_request_as_acknowledgement():
    # "好" is a substring of countless real asks; matching must be exact.
    route = EntryRouter().route(
        "我最近手头好紧，帮我看看",
        chat_history=[{"role": "assistant", "content": "先前分析"}],
    )

    assert route.execution_path == "cfo_analysis"
    assert route.run_finance_pipeline is True


def test_router_does_not_treat_english_sentence_as_greeting():
    # "this" contains "hi"; greetings must anchor as whole words.
    route = EntryRouter().route(
        "this is my first time here, what can you do", chat_history=[]
    )

    assert route.execution_path == "clarification"
    assert route.run_finance_pipeline is False


def test_router_sends_why_with_dates_to_analysis_not_evidence():
    # Digits mean a fresh ledger question, not the previous answer's evidence.
    route = EntryRouter().route(
        "为什么6月10日花这么多",
        chat_history=[{"role": "assistant", "content": "先前分析"}],
    )

    assert route.execution_path == "cfo_analysis"
    assert route.run_finance_pipeline is True


def test_router_keeps_pure_social_messages_light():
    router = EntryRouter()
    hist = [{"role": "assistant", "content": "先前分析"}]

    for message in ("哈哈哈哈哈", "好的，那就这样办", "谢谢！", "hi there", "你好呀"):
        route = router.route(message, chat_history=hist)
        assert route.execution_path == "light_reply", message
        assert route.run_finance_pipeline is False, message


def test_router_routes_colloquial_money_trouble_to_analysis():
    route = EntryRouter().route("我是月光族怎么办", chat_history=[])

    assert route.intent == "finance_query"
    assert route.run_finance_pipeline is True

# --- Hybrid router: classifier band, guard adjudication, fallback ---

import pytest

from app.models.routing import RouteCandidate
from app.runtime.orchestration.entry_router import RouteGuard
from app.runtime.orchestration.route_classifier import ModelRouteClassifier


class FakeClassifier:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = []

    def available(self):
        return True

    async def classify(self, message, *, has_prior_context):
        self.calls.append(message)
        return self.candidate


def _model_candidate(intent, path, confidence=0.9):
    return RouteCandidate(
        intent=intent,
        execution_path=path,
        confidence=confidence,
        reason_code="test",
        source="model",
    )


@pytest.mark.asyncio
async def test_decide_uses_model_candidate_for_ambiguous_band():
    classifier = FakeClassifier(_model_candidate("finance_query", "cfo_analysis"))
    router = EntryRouter(classifier=classifier)

    decision = await router.decide("帮我盘一盘最近的情况", chat_history=[])

    assert decision.route.execution_path == "cfo_analysis"
    assert decision.route.run_finance_pipeline is True
    assert decision.candidate.source == "model"
    assert decision.guard_reason == "model_accepted"
    assert decision.classifier_status == "called"


@pytest.mark.asyncio
async def test_decide_never_calls_classifier_for_decisive_messages():
    classifier = FakeClassifier(_model_candidate("small_talk", "light_reply"))
    router = EntryRouter(classifier=classifier)

    social = await router.decide("你好", chat_history=[])
    finance = await router.decide("这个月购物支出占比多少？", chat_history=[])

    assert classifier.calls == []
    assert social.classifier_status == "skipped"
    assert social.route.execution_path == "light_reply"
    assert finance.route.execution_path == "cfo_analysis"


@pytest.mark.asyncio
async def test_guard_downgrades_contextless_evidence_candidate():
    classifier = FakeClassifier(_model_candidate("evidence_request", "evidence_only"))
    router = EntryRouter(classifier=classifier)

    decision = await router.decide("凭什么给出这样的判断呢", chat_history=[])

    assert decision.route.execution_path == "clarification"
    assert decision.guard_reason == "no_context_downgrade"


def test_guard_escalates_model_light_reply_with_finance_facts():
    guard = RouteGuard()
    candidate = _model_candidate("small_talk", "light_reply")

    route, reason = guard.adjudicate(
        candidate, message="随便看看 3000 块去哪了", has_prior_context=False
    )

    assert route.execution_path == "cfo_analysis"
    assert route.run_finance_pipeline is True
    assert reason == "lexical_finance_override"


def test_guard_promotes_contextless_followup_candidate():
    guard = RouteGuard()
    candidate = _model_candidate("follow_up", "cfo_followup")

    route, reason = guard.adjudicate(
        candidate, message="然后呢", has_prior_context=False
    )

    assert route.execution_path == "cfo_analysis"
    assert reason == "no_context_promotion"


@pytest.mark.asyncio
async def test_decide_falls_back_when_classifier_returns_nothing():
    class FailingClassifier:
        def available(self):
            return True

        async def classify(self, message, *, has_prior_context):
            return None

    router = EntryRouter(classifier=FailingClassifier())

    decision = await router.decide("帮我盘一盘最近的情况", chat_history=[])

    assert decision.classifier_status == "failed"
    assert decision.candidate.source == "fallback"
    # v1 tail behavior preserved: question-like → clarification
    assert decision.route.execution_path == "clarification"


@pytest.mark.asyncio
async def test_decide_without_classifier_matches_sync_route():
    router = EntryRouter()
    for message, history in [
        ("帮我盘一盘最近的情况", []),
        ("你好", []),
        ("为什么这样建议？", [{"role": "assistant", "content": "x"}]),
    ]:
        decision = await router.decide(message, chat_history=history)
        assert decision.route == router.route(message, chat_history=history)
        assert decision.classifier_status == "skipped"


@pytest.mark.asyncio
async def test_classifier_parses_strict_json_and_rejects_bad_enums():
    from types import SimpleNamespace

    class FakeLLM:
        def __init__(self, data):
            self.data = data

        def available(self, profile="router"):
            return True

        async def generate_json(self, prompt, *, profile="router", system=""):
            return SimpleNamespace(data=self.data)

    good = ModelRouteClassifier(
        lambda: FakeLLM(
            {
                "intent": "finance_query",
                "execution_path": "cfo_analysis",
                "confidence": 1.7,
                "reason_code": "colloquial_finance",
            }
        )
    )
    candidate = await good.classify("感觉这个月有点失控了", has_prior_context=False)
    assert candidate is not None
    assert candidate.source == "model"
    assert candidate.confidence == 1.0  # clamped, observability-only

    bad = ModelRouteClassifier(
        lambda: FakeLLM({"intent": "run_sql", "execution_path": "cfo_analysis"})
    )
    assert await bad.classify("x", has_prior_context=False) is None


def test_route_classify_hidden_from_user_steps():
    from app.runtime.observability.steps_projection import project_steps

    steps = project_steps(
        {
            "tool_calls": [{"name": "route_classify", "status": "called"}],
            "handoffs": [],
        }
    )

    assert steps == []
