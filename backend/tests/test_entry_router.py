from app.runtime.orchestration.entry_router import EntryRouter

# Proven finance context: session_memory is written only by the finance
# pipeline, so referring-back intents key on it — never on raw chat text.
_FINANCE_MEMORY = {
    "session_memory": {
        "last_topic": {"capability": "spending_review", "focus": "shopping"},
        "last_result_brief": "shopping 支出偏高，建议复核大额消费。",
    }
}


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
        memory_context=_FINANCE_MEMORY,
    )

    assert route.intent == "follow_up"
    assert route.execution_path == "cfo_followup"
    assert route.run_finance_pipeline is True


def test_router_routes_evidence_request_without_rerun():
    route = EntryRouter().route(
        "为什么这样建议？",
        chat_history=[{"role": "assistant", "content": "建议复核 shopping 支出"}],
        memory_context=_FINANCE_MEMORY,
    )

    assert route.intent == "evidence_request"
    assert route.execution_path == "evidence_only"
    assert route.run_finance_pipeline is False
    assert route.emit_steps is False
    assert route.attach_evidence is True


def test_evidence_request_needs_proven_finance_memory_not_just_chat():
    # A capability intro is an assistant message too; without finance
    # session memory the router must not pretend citations exist.
    capability_history = [
        {"role": "user", "content": "你有什么用"},
        {"role": "assistant", "content": "我是你的个人 CFO，可以分析支出、预算和现金流。"},
    ]

    route = EntryRouter().route(
        "为什么这样建议？", chat_history=capability_history
    )

    assert route.execution_path != "evidence_only"
    assert route.attach_evidence is False

    with_memory = EntryRouter().route(
        "为什么这样建议？",
        chat_history=capability_history,
        memory_context=_FINANCE_MEMORY,
    )
    assert with_memory.execution_path == "evidence_only"


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


# --- Hybrid router: semantic intent layer + route resolver ---

import pytest

from app.runtime.orchestration.router import (
    ClassifierInput,
    IntentCandidate,
    MessageFacts,
    ModelIntentClassifier,
    RouteResolver,
    build_classifier_input,
)


class FakeClassifier:
    def __init__(self, candidate):
        self.candidate = candidate
        self.payloads = []

    def available(self):
        return True

    async def classify(self, payload):
        self.payloads.append(payload)
        return self.candidate


def _model_intent(intent, confidence=0.9):
    return IntentCandidate(
        intent=intent, confidence=confidence, reason_code="test", source="model"
    )


@pytest.mark.asyncio
async def test_decide_uses_model_intent_for_colloquial_finance():
    classifier = FakeClassifier(_model_intent("finance_question"))
    router = EntryRouter(classifier=classifier)

    decision = await router.decide("帮我盘一盘最近的情况", chat_history=[])

    assert decision.route.execution_path == "cfo_analysis"
    assert decision.route.run_finance_pipeline is True
    assert decision.candidate.source == "model"
    assert decision.guard_reason == "model_accepted"
    assert decision.classifier_status == "called"
    # classifier receives bounded typed input, never the raw pipeline
    payload = classifier.payloads[0]
    assert isinstance(payload, ClassifierInput)
    assert payload.message == "帮我盘一盘最近的情况"


@pytest.mark.asyncio
async def test_social_shortcuts_never_call_the_classifier():
    classifier = FakeClassifier(_model_intent("finance_question"))
    router = EntryRouter(classifier=classifier)

    greeting = await router.decide("你好", chat_history=[])
    ack = await router.decide("哈哈", chat_history=[])

    assert classifier.payloads == []
    assert greeting.classifier_status == "skipped"
    assert greeting.route.execution_path == "light_reply"
    assert ack.route.execution_path == "light_reply"


@pytest.mark.asyncio
async def test_capability_question_stays_light():
    classifier = FakeClassifier(_model_intent("capability_question"))
    router = EntryRouter(classifier=classifier)

    decision = await router.decide("你有什么用？", chat_history=[])

    assert decision.route.execution_path == "light_reply"
    assert decision.route.run_finance_pipeline is False


def test_resolver_escalates_social_intent_with_finance_facts():
    facts = MessageFacts.from_message("随便看看 3000 块去哪了")
    resolver = RouteResolver()

    route, reason = resolver.resolve(_model_intent("small_talk"), facts)

    assert route.execution_path == "cfo_analysis"
    assert route.run_finance_pipeline is True
    assert reason == "lexical_finance_override"


def test_resolver_downgrades_referring_intents_with_chat_but_no_finance_memory():
    # Plain chat history (assistant capability intro) without finance
    # session memory is NOT finance context for the resolver either.
    facts = MessageFacts.from_message(
        "凭什么给出这样的判断呢",
        chat_history=[{"role": "assistant", "content": "我是你的个人 CFO 助手。"}],
        memory_context=None,
    )
    assert facts.has_prior_chat_history is True
    assert facts.has_prior_finance_context is False
    resolver = RouteResolver()

    evidence_route, _ = resolver.resolve(_model_intent("evidence_request"), facts)
    followup_route, _ = resolver.resolve(_model_intent("finance_followup"), facts)

    assert evidence_route.execution_path == "clarification"
    assert followup_route.execution_path == "clarification"


def test_resolver_downgrades_contextless_referring_intents():
    facts = MessageFacts.from_message("凭什么给出这样的判断呢")
    resolver = RouteResolver()

    evidence_route, evidence_reason = resolver.resolve(
        _model_intent("evidence_request"), facts
    )
    followup_route, followup_reason = resolver.resolve(
        _model_intent("finance_followup"), facts
    )

    # No prior finance context: never pretend citations exist.
    assert evidence_route.execution_path == "clarification"
    assert evidence_reason == "no_context_downgrade"
    assert followup_route.execution_path == "clarification"
    assert followup_reason == "no_context_downgrade"


def test_resolver_low_confidence_does_not_blindly_run_pipeline():
    resolver = RouteResolver()

    vague = MessageFacts.from_message("帮我盘一盘最近的情况")
    route, reason = resolver.resolve(_model_intent("finance_question", 0.2), vague)
    assert route.execution_path == "clarification"
    assert reason == "low_confidence_downgrade"

    # Verifiable finance facts keep the pipeline despite low confidence.
    grounded = MessageFacts.from_message("看下那笔 3000 的")
    route, reason = resolver.resolve(_model_intent("finance_question", 0.2), grounded)
    assert route.execution_path == "cfo_analysis"


@pytest.mark.asyncio
async def test_decide_falls_back_when_classifier_returns_nothing():
    class FailingClassifier:
        def available(self):
            return True

        async def classify(self, payload):
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
        ("这个月购物支出占比多少？", []),
    ]:
        decision = await router.decide(message, chat_history=history)
        assert decision.route == router.route(message, chat_history=history)
        assert decision.classifier_status == "skipped"


@pytest.mark.asyncio
async def test_model_classifier_parses_intent_only_json():
    from types import SimpleNamespace

    class FakeLLM:
        def __init__(self, data):
            self.data = data
            self.prompts = []

        def available(self, profile="router"):
            return True

        async def generate_json(self, prompt, *, profile="router", system=""):
            self.prompts.append((prompt, system))
            return SimpleNamespace(data=self.data)

    facts = MessageFacts.from_message("感觉这个月有点失控了")
    payload = build_classifier_input("感觉这个月有点失控了", facts)

    good_llm = FakeLLM(
        {"intent": "finance_question", "confidence": 1.7, "reason_code": "colloquial"}
    )
    candidate = await ModelIntentClassifier(lambda: good_llm).classify(payload)
    assert candidate is not None
    assert candidate.source == "model"
    assert candidate.confidence == 1.0  # clamped, observability-only
    # the model is never offered an execution_path vocabulary
    prompt, system = good_llm.prompts[0]
    assert "execution_path" not in prompt
    assert "NOT output an execution_path" in system

    # invalid JSON payloads and out-of-enum intents fall back, never crash
    for bad in ({}, {"intent": "run_sql"}, {"intent": "cfo_analysis"}):
        assert await ModelIntentClassifier(lambda: FakeLLM(bad)).classify(payload) is None


def test_route_classify_hidden_from_user_steps():
    from app.runtime.observability.steps_projection import project_steps

    steps = project_steps(
        {
            "tool_calls": [{"name": "route_classify", "status": "called"}],
            "handoffs": [],
        }
    )

    assert steps == []
