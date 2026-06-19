from local_qq_agent.agent.run_log import RunSessionLogExporter
from local_qq_agent.memory import SQLiteMemoryStore


def test_run_session_log_exports_clean_events_and_style_summary(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.append_event(
        source="Tsubashimo Nanato",
        kind="group_message",
        content="raw old block",
        metadata={"sender_name": "Tsubashimo Nanato", "clean_text": "clean message"},
    )
    store.append_event(
        source="agent",
        kind="assistant_reply",
        content="reply text",
        metadata={"user_name": "Tsubashimo Nanato", "thinking_level": 1, "web_used": False},
    )
    store.append_event(
        source="agent",
        kind="behavior_feedback",
        content="low score",
        metadata={"score_value": 0.2, "score_note": "interrupted"},
    )
    store.append_event(source="agent", kind="raw_provider_trace", content="must not export", metadata={})

    run_log = RunSessionLogExporter(store).build(
        started_after_event_id=0,
        style_learning_target_user="Tsubashimo Nanato",
    )
    payload = run_log.to_dict()

    assert payload["event_count"] == 3
    assert all(event["kind"] != "raw_provider_trace" for event in payload["events"])
    assert payload["events"][0]["text"] == "clean message"
    assert payload["style_learning"]["target_user_message_count"] == 1
    assert payload["style_learning"]["assistant_reply_count"] == 1
    assert payload["style_learning"]["low_score_feedback_count"] == 1
