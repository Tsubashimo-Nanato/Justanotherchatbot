from local_qq_agent.memory import SQLiteMemoryStore
from local_qq_agent.server.debug_timeline import build_debug_timeline


def test_debug_timeline_keeps_human_readable_decision_fields(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.append_event(
        source="Tsubashimo Nanato",
        kind="group_message",
        content="raw block with noise",
        metadata={
            "sender_name": "Tsubashimo Nanato",
            "clean_text": "going to work",
            "agent_action": "queued",
            "agent_reason": "queued_for_decision",
            "window_title": "QQ noisy title",
        },
    )
    store.append_event(
        source="loop",
        kind="loop_decision",
        content="reply decision",
        metadata={
            "sender_name": "Tsubashimo Nanato",
            "message_text": "going to work",
            "action": "reply",
            "reason": "direct_followup",
            "agent_reply": "then eat first",
            "sent": True,
            "prompt_tokens": 1200,
            "completion_tokens": 8,
            "total_tokens": 1208,
            "token_usage": {
                "local": {"total": {"prompt": 30, "completion": 4, "total": 34, "latency_seconds": 0.2}},
                "api": {
                    "total": {
                        "input": 1200,
                        "output": 8,
                        "total": 1208,
                        "cached": 900,
                        "reasoning": 2,
                        "cost_ticks": 10,
                        "latency_seconds": 2.5,
                    }
                },
            },
            "latency_seconds": 2.5,
            "web_used": False,
        },
    )

    timeline = build_debug_timeline(store.recent_events(limit=20), limit=10)

    assert timeline[0]["who"] == "Tsubashimo Nanato"
    assert timeline[0]["message"] == "going to work"
    assert "window_title" not in timeline[0]
    assert timeline[1]["decision"] == "reply"
    assert timeline[1]["reply"] == "then eat first"
    assert timeline[1]["tokens"]["prompt"] == 1200
    assert timeline[1]["tokens"]["local"]["total"] == 34
    assert timeline[1]["tokens"]["api"]["cached"] == 900


def test_debug_timeline_collapses_linked_assistant_reply(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    assistant_event = store.append_event(
        source="agent",
        kind="assistant_reply",
        content="still thinking, you?",
        metadata={"reason": "direct_quote_reply"},
    )
    store.append_event(
        source="loop",
        kind="loop_decision",
        content="reply decision",
        metadata={
            "assistant_event_id": assistant_event.id,
            "sender_name": "Tsubashimo Nanato",
            "message_text": "going to the store later",
            "action": "reply",
            "reason": "direct_quote_reply",
            "sent": True,
            "metadata": {"cleaned_reply": "still thinking, you?"},
        },
    )

    timeline = build_debug_timeline(store.recent_events(limit=20), limit=10)

    assert len(timeline) == 1
    assert timeline[0]["kind"] == "loop_decision"
    assert timeline[0]["reply"] == "still thinking, you?"
