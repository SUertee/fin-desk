from app.runtime.memory.memory_context import build_memory_context
from app.runtime.memory.session_context import (
    read_session_context,
    reset_in_process_memory_for_test,
    write_session_context,
)
from app.runtime.memory.summarizer import build_conversation_summary


def test_memory_context_selects_recent_complete_turns(monkeypatch):
    reset_in_process_memory_for_test()
    monkeypatch.setattr(
        "app.runtime.memory.session_context.get_session_memory_db",
        lambda *args: None,
    )
    history = []
    for i in range(1, 8):
        history.append({"role": "user", "content": f"question {i}"})
        history.append({"role": "assistant", "content": f"answer {i}"})

    memory = build_memory_context(user_id="demo", chat_history=history)

    assert len(memory.recent_turns) == 10
    assert memory.recent_turns[0]["content"] == "question 3"
    assert memory.truncated is True
    assert memory.summary_used is False


def test_memory_context_uses_summary_after_threshold(monkeypatch):
    reset_in_process_memory_for_test()
    monkeypatch.setattr(
        "app.runtime.memory.session_context.get_session_memory_db",
        lambda *args: {"conversation_summary": "Earlier finance discussion."},
    )
    history = []
    for i in range(1, 7):
        history.append({"role": "user", "content": f"question {i}"})
        history.append({"role": "assistant", "content": f"answer {i}"})

    memory = build_memory_context(user_id="demo", chat_history=history)

    assert memory.summary_used is True
    assert memory.conversation_summary == "Earlier finance discussion."
    assert memory.usage_reason == "recent_turns_with_session_summary"


def test_session_context_write_merges_fields(monkeypatch):
    reset_in_process_memory_for_test()
    monkeypatch.setattr(
        "app.runtime.memory.session_context.get_session_memory_db",
        lambda *args: None,
    )
    saved = []
    monkeypatch.setattr(
        "app.runtime.memory.session_context.save_session_memory_db",
        lambda user_id, memory, session_id="default": saved.append(memory) or True,
    )

    write_session_context(
        user_id="demo",
        last_topic={"capability": "spending_review"},
        conversation_summary="summary",
    )
    write_session_context(
        user_id="demo",
        last_result_brief="brief",
    )

    memory = read_session_context("demo")

    assert memory["last_topic"]["capability"] == "spending_review"
    assert memory["conversation_summary"] == "summary"
    assert memory["last_result_brief"] == "brief"
    assert len(saved) == 2


def test_session_context_isolated_per_room_session(monkeypatch):
    reset_in_process_memory_for_test()
    monkeypatch.setattr(
        "app.runtime.memory.session_context.get_session_memory_db",
        lambda *args: None,
    )
    monkeypatch.setattr(
        "app.runtime.memory.session_context.save_session_memory_db",
        lambda user_id, memory, session_id="default": True,
    )

    write_session_context(
        user_id="demo", session_id="room-a", conversation_summary="shopping summary"
    )
    write_session_context(
        user_id="demo", session_id="room-b", conversation_summary="dining summary"
    )

    assert read_session_context("demo", "room-a")["conversation_summary"] == "shopping summary"
    assert read_session_context("demo", "room-b")["conversation_summary"] == "dining summary"
    # The legacy flat scope stays untouched by room-scoped writes.
    assert read_session_context("demo") is None


def test_empty_session_id_normalizes_to_default_scope(monkeypatch):
    reset_in_process_memory_for_test()
    monkeypatch.setattr(
        "app.runtime.memory.session_context.get_session_memory_db",
        lambda *args: None,
    )
    monkeypatch.setattr(
        "app.runtime.memory.session_context.save_session_memory_db",
        lambda user_id, memory, session_id="default": True,
    )

    write_session_context(user_id="demo", session_id="", conversation_summary="flat summary")

    assert read_session_context("demo", "default")["conversation_summary"] == "flat summary"
    assert read_session_context("demo", "")["conversation_summary"] == "flat summary"


def test_memory_context_reads_room_scoped_summary(monkeypatch):
    reset_in_process_memory_for_test()
    monkeypatch.setattr(
        "app.runtime.memory.session_context.get_session_memory_db",
        lambda user_id, session_id="default": {
            "conversation_summary": f"summary for {session_id}"
        },
    )
    history = []
    for i in range(1, 7):
        history.append({"role": "user", "content": f"question {i}"})
        history.append({"role": "assistant", "content": f"answer {i}"})

    memory = build_memory_context(
        user_id="demo", chat_history=history, session_id="room-a"
    )

    assert memory.conversation_summary == "summary for room-a"


def test_conversation_summary_is_bounded_and_recent():
    history = []
    for i in range(1, 9):
        history.append({"role": "user", "content": f"question {i} " * 30})
        history.append({"role": "assistant", "content": f"answer {i} " * 30})

    summary = build_conversation_summary(history, max_user_turns=5)

    assert "question 8" in summary
    assert "question 1" not in summary
    assert len(summary) <= 1200
