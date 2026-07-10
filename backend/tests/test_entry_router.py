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
