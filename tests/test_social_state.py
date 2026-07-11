from local_qq_agent.agent import PersonaGuard, SocialStateTracker
from local_qq_agent.agent.context import ContextBuilder
from local_qq_agent.config import PersonaConfig
from local_qq_agent.memory import SQLiteMemoryStore


def build_guard():
    return PersonaGuard(
        PersonaConfig(
            name="demo",
            language="zh-CN",
            summary="neutral test persona",
            style_rules=("stay concise",),
            ooc_triggers=("ignore previous",),
            fallback_reply="blocked",
        )
    )


def test_boundary_hit_temporarily_guards_mood_and_lowers_affinity(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    tracker = SocialStateTracker(store)

    snapshot = tracker.record_boundary_hit(user_name="tester", reason="ooc")

    assert snapshot.global_mood == "guarded"
    assert snapshot.mood_intensity == 0.25
    assert snapshot.affinity == 0.45
    assert snapshot.source == "boundary_hit"
    assert any(event.kind == "social_state_update" for event in store.recent_events())
    assert store.recent_memories(limit=1)[0].kind == "relationship"


def test_manual_override_sets_mood_and_user_affinity(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    tracker = SocialStateTracker(store)

    snapshot = tracker.override(
        user_name="tester",
        global_mood="irritated",
        mood_intensity=0.4,
        affinity=0.2,
        note="manual test",
    )

    assert snapshot.global_mood == "irritated"
    assert snapshot.mood_intensity == 0.4
    assert snapshot.affinity == 0.2
    assert snapshot.source == "manual_override"


def test_contact_initialization_sets_default_affinity_once(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    tracker = SocialStateTracker(store)

    first = tracker.ensure_contact(user_name="target user", initial_affinity=1.0, source="target_contact_seed")
    second = tracker.ensure_contact(user_name="target user", initial_affinity=0.5, source="visible_contact_seed")

    assert first.affinity == 1.0
    assert first.source == "target_contact_seed"
    assert second.affinity == 1.0
    assert second.source == "target_contact_seed"
    assert [event.kind for event in store.recent_events()].count("user_profile_seen") == 1


def test_context_builder_includes_social_state_lines(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    tracker = SocialStateTracker(store)
    tracker.override(user_name="tester", global_mood="guarded", mood_intensity=0.3, affinity=0.25)
    builder = ContextBuilder(store, build_guard(), tracker)

    built = builder.build("tester", "hello")

    assert any("global mood: guarded" in line for line in built.memory_lines)
    assert any("user affinity for tester: 0.25" in line for line in built.memory_lines)


def test_context_builder_keeps_stable_prefix_when_runtime_context_changes(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    tracker = SocialStateTracker(store)
    builder = ContextBuilder(store, build_guard(), tracker)

    first = builder.build("tester", "hello")
    store.add_memory(kind="fact", summary="tester likes udon", confidence=0.8)
    tracker.override(user_name="tester", global_mood="neutral", mood_intensity=0.0, affinity=0.9)
    second = builder.build("tester", "udon?")

    assert first.messages[0] == second.messages[0]
    assert "tester likes udon" not in first.messages[0]["content"]
    assert "tester likes udon" in second.messages[1]["content"]
    assert "user affinity for tester: 0.90" in second.messages[1]["content"]


def test_context_builder_does_not_include_unrelated_recent_memory(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    builder = ContextBuilder(store, build_guard())
    store.add_memory(kind="fact", summary="Tsubashimo Nanato: 蓝色 represents 114514", confidence=0.9)
    store.add_memory(kind="working_context", summary="Tsubashimo Nanato: recent personal context: 早上没吃饭", confidence=0.7)

    built = builder.build("Tsubashimo Nanato", "今天吃什么比较好")

    assert any("早上没吃饭" in line for line in built.memory_lines)
    assert not any("蓝色" in line for line in built.memory_lines)


def test_context_builder_keeps_relevant_mapping_memory(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    builder = ContextBuilder(store, build_guard())
    store.add_memory(kind="fact", summary="Tsubashimo Nanato: 蓝色 represents 114514", confidence=0.9)
    store.add_memory(kind="fact", summary="Tsubashimo Nanato: 红色 represents 1919810", confidence=0.9)

    built = builder.build("Tsubashimo Nanato", "红色呢")

    assert any("红色" in line and "1919810" in line for line in built.memory_lines)


def test_context_builder_memory_summary_can_use_recent_memories(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    builder = ContextBuilder(store, build_guard())
    store.add_memory(kind="fact", summary="Tsubashimo Nanato: 蓝色 represents 114514", confidence=0.9)
    store.add_memory(kind="plan", summary="Tsubashimo Nanato: plan: 下午去学校", confidence=0.7)

    built = builder.build("Tsubashimo Nanato", "最后总结一下你刚刚记住了什么")

    assert any("蓝色" in line for line in built.memory_lines)
    assert any("下午去学校" in line for line in built.memory_lines)


def test_context_builder_schedule_reference_can_use_plan_memory(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    builder = ContextBuilder(store, build_guard())
    store.add_memory(kind="plan", summary="Tsubashimo Nanato: plan: 下午去学校", confidence=0.7)

    built = builder.build("Tsubashimo Nanato", "我下午那个安排是什么")

    assert any("下午去学校" in line for line in built.memory_lines)


def test_user_profiles_include_seen_messages_and_manual_profile(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    tracker = SocialStateTracker(store)
    store.append_event(
        source="visible user",
        kind="group_message",
        content="hello",
        metadata={"sender_name": "visible user", "clean_text": "hello"},
    )
    tracker.override_profile(
        user_name="manual user",
        affinity=0.8,
        language_preference="mixed",
        relationship_notes="debug note",
    )

    profiles = {profile["user_name"]: profile for profile in tracker.user_profiles()}

    assert profiles["visible user"]["message_count"] == 1
    assert profiles["visible user"]["affinity"] == 0.5
    assert profiles["manual user"]["affinity"] == 0.8
    assert profiles["manual user"]["language_preference"] == "mixed"


def test_context_builder_api_events_are_opt_in(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    guard = build_guard()
    store.append_event(
        source="tester",
        kind="group_message",
        content="first api turn",
        metadata={
            "origin": "api",
            "agent_action": "reply",
            "sender_name": "tester",
            "clean_text": "first api turn",
        },
    )

    default_context = ContextBuilder(store, guard).build("tester", "what did I say")
    opt_in_context = ContextBuilder(store, guard, include_api_events=True).build("tester", "what did I say")

    assert not any("first api turn" in line for line in default_context.recent_lines)
    assert any("first api turn" in line for line in opt_in_context.recent_lines)
def test_onebot_user_id_keeps_profile_stable_when_group_card_changes(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    tracker = SocialStateTracker(store)

    first = tracker.ensure_contact(user_name="old card", user_id="12345", initial_affinity=0.8)
    renamed = tracker.ensure_contact(user_name="new card", user_id="12345", initial_affinity=0.5)

    assert first.user_name == "old card"
    assert renamed.user_name == "old card"
    relationships = [item for item in store.recent_memories(limit=20) if item.kind == "relationship"]
    assert len(relationships) == 1
    assert relationships[0].metadata["external_user_id"] == "12345"
    assert "new card" in relationships[0].metadata["aliases"]
