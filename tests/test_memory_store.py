from local_qq_agent.memory import SQLiteMemoryStore


def test_memory_store_records_events_and_memories(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")

    event = store.append_event(source="tester", kind="group_message", content="记住我喜欢冷静一点的回复")
    memory = store.add_memory(kind="preference", summary="tester likes concise replies")

    assert event.id > 0
    assert memory.id > 0
    assert store.status()["event_count"] == 1
    assert store.status()["memory_count"] == 1

    results = store.search_memories("concise")
    assert len(results) == 1
    assert results[0].summary == "tester likes concise replies"


def test_memory_store_rejects_empty_event_content(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")

    try:
        store.append_event(source="tester", kind="group_message", content=" ")
    except ValueError as error:
        assert "content" in str(error)
    else:
        raise AssertionError("empty event content was accepted")


def test_memory_store_deletes_matching_memories(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    keep = store.add_memory(kind="preference", summary="tester likes quiet replies")
    delete = store.add_memory(kind="fact", summary="tester temporary code is 1234")

    deleted = store.delete_memories_matching("temporary code")

    assert [memory.id for memory in deleted] == [delete.id]
    remaining = store.recent_memories(limit=10)
    assert [memory.id for memory in remaining] == [keep.id]


def test_memory_store_updates_memory_by_id(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    memory = store.add_memory(kind="working_context", summary="old summary", confidence=0.4)

    updated = store.update_memory(
        memory_id=memory.id,
        kind="preference",
        summary="updated summary",
        confidence=0.9,
        metadata={"source": "test"},
    )

    assert updated.id == memory.id
    assert updated.kind == "preference"
    assert updated.summary == "updated summary"
    assert updated.confidence == 0.9
    assert updated.metadata["source"] == "test"


def test_memory_store_deletes_memory_by_id(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    keep = store.add_memory(kind="preference", summary="keep")
    delete = store.add_memory(kind="fact", summary="delete")

    deleted = store.delete_memory_by_id(delete.id)

    assert deleted is not None
    assert deleted.id == delete.id
    assert [memory.id for memory in store.recent_memories(limit=10)] == [keep.id]


def test_recent_events_can_return_newest_first(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    first = store.append_event(source="tester", kind="group_message", content="first")
    second = store.append_event(source="tester", kind="group_message", content="second")

    assert [event.id for event in store.recent_events(limit=2)] == [first.id, second.id]
    assert [event.id for event in store.recent_events(limit=2, newest_first=True)] == [second.id, first.id]
