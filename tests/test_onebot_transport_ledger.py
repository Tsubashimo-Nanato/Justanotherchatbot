from local_qq_agent.memory import SQLiteMemoryStore


def test_transport_message_is_inserted_once_across_event_and_history(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    fields = {
        "canonical_turn_id": "onebot:100:300",
        "message_id": "300",
        "self_id": "100",
        "group_id": "200",
        "user_id": "400",
        "sender_name": "owner",
        "message_text": "hello",
    }

    assert store.observe_transport_turn(**fields, metadata={"source": "event"}) is True
    assert store.observe_transport_turn(**fields, metadata={"source": "redelivery"}) is False
    assert store.observe_transport_turn(**fields, metadata={"source": "history"}) is False
    assert len(store.recent_transport_turns()) == 1


def test_transport_state_records_send_result_without_reopening_turn(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.observe_transport_turn(
        canonical_turn_id="onebot:100:300",
        message_id="300",
        self_id="100",
        group_id="200",
        user_id="400",
        sender_name="owner",
        message_text="hello",
    )

    store.update_transport_turn(
        "onebot:100:300",
        state="completed",
        metadata={"outbound_message_id": "900"},
    )

    row = store.recent_transport_turns()[0]
    assert row["state"] == "completed"
    assert row["metadata"]["outbound_message_id"] == "900"
