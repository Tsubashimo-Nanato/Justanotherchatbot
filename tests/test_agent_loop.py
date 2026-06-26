from local_qq_agent.config import QQConfig
from local_qq_agent.memory import SQLiteMemoryStore
from local_qq_agent.qq import QQChatMessage, QQReadResult
from local_qq_agent.server.agent_loop import AgentLoop, LoopDecision


def test_agent_loop_deduplicates_visible_message_after_coordinate_shift():
    loop = build_loop()

    assert not loop._message_seen("target user", "hello", "fp-1")

    loop._remember_seen_message("target user", "hello", "fp-1")

    assert loop._message_seen("target user", "hello", "fp-2")


def test_agent_loop_keeps_same_visible_message_seen_after_two_minutes():
    loop = build_loop()
    loop._remember_seen_message("target user", "roast chicken good", "fp-old")

    assert loop._message_seen("target user", "roast chicken good", "fp-new-coordinate")


def test_agent_loop_hydrates_seen_messages_from_recent_loop_decisions(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.append_event(
        source="loop",
        kind="loop_decision",
        content="reply: model_reply",
        metadata={
            "sender_name": "target user",
            "message_text": "roast chicken good",
            "metadata": {"message_identity": "target user|roast chicken good"},
        },
    )

    loop = build_loop(store=store)

    assert loop._message_seen("target user", "roast chicken good", "fp-new-coordinate")


def test_agent_loop_persists_decision_index_fields(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    loop = build_loop(store=store)
    decision = LoopDecision(
        created_at=1.0,
        message_text="roast chicken good",
        sender_name="target user",
        action="reply",
        reason="model_reply",
        sent=True,
        send_reason="sent",
        elapsed_seconds=1.2,
        metadata={
            "message_identity": "target user|roast chicken good",
            "provider_trace_id": "trace-1",
            "prompt_tokens": 12,
            "completion_tokens": 3,
        },
    )

    loop._remember_decision(decision)

    event = store.recent_events()[0]
    assert event.metadata["message_identity"] == "target user|roast chicken good"
    assert event.metadata["provider_trace_id"] == "trace-1"
    assert event.metadata["prompt_tokens"] == 12
    assert event.metadata["metadata"]["message_identity"] == "target user|roast chicken good"


def test_agent_loop_stable_identity_ignores_invisible_text_noise():
    loop = build_loop()
    loop._remember_seen_message("Target User", "roast\u200b  chicken good", "fp-old")

    assert loop._message_seen("target user", "roast chicken good", "fp-new")


def test_agent_loop_uses_clean_identity_for_inflight_duplicate_suppression():
    loop = build_loop()
    polluted = message("old bot reply\n[debug elapsed=10s, prompt_tokens=99]\nwhat time is it .detail", "fp-1", top=100)
    same_turn = message("what time is it .detail", "fp-2", top=120)

    enqueued = loop._enqueue_visible_targets([polluted])
    queued = enqueued[0]
    loop._pending_messages.popleft()
    loop._turn_ledger.mark_inflight(queued.identity)

    repeated = loop._enqueue_visible_targets([same_turn])

    assert queued.text == "what time is it .detail"
    assert queued.raw_text != queued.text
    assert repeated == []


def test_agent_loop_backs_off_after_idle_reads():
    loop = build_loop(idle_poll_interval_seconds=5.0, idle_poll_after_ticks=2)

    assert loop._next_poll_interval() == 1.0

    loop._record_read_activity(False)
    assert loop._next_poll_interval() == 1.0

    loop._record_read_activity(False)
    assert loop._next_poll_interval() == 5.0
    assert loop.status()["current_poll_interval_seconds"] == 5.0

    loop._record_read_activity(True)
    assert loop._next_poll_interval() == 1.0
    assert loop.status()["idle_read_ticks"] == 0


def test_agent_loop_merges_same_sender_messages_after_quiet_period():
    loop = build_loop()
    first = message("沐浴露", "fp-bath-1", top=100)
    second = message("好闻", "fp-bath-2", top=150)

    assert loop._enqueue_visible_targets([first], respect_quiet_period=True, now=10.0) == []
    assert loop.status()["aggregating_message_count"] == 1

    assert loop._enqueue_visible_targets([second], respect_quiet_period=True, now=12.0) == []

    enqueued = loop._enqueue_visible_targets([], respect_quiet_period=True, now=19.0)

    assert len(enqueued) == 1
    assert enqueued[0].text == "沐浴露\n好闻"
    assert enqueued[0].turn.reason == "quiet_period_merged"
    assert loop.status()["aggregating_message_count"] == 0
    assert loop.status()["pending_message_count"] == 1
    assert not loop._turn_ledger.can_enqueue(enqueued[0].identity, "fp-bath-1")
    assert not loop._turn_ledger.can_enqueue(enqueued[0].identity, "fp-bath-2")


def test_agent_loop_does_not_duplicate_buffered_coordinate_shift():
    loop = build_loop()
    original = message("还没想好", "fp-noodle-1", top=100)
    shifted = message("还没想好", "fp-noodle-2", top=130)

    loop._enqueue_visible_targets([original], respect_quiet_period=True, now=10.0)
    loop._enqueue_visible_targets([shifted], respect_quiet_period=True, now=11.0)

    assert loop.status()["aggregating_messages"][0]["message_count"] == 1


def test_agent_loop_marks_cleaned_message_seen_after_polluted_raw_block():
    loop = build_loop()
    polluted = message("old bot reply\n[debug elapsed=10s, prompt_tokens=99]\nwhat time is it .detail", "fp-1", top=100)
    cleaned = loop._clean_visible_message(polluted)

    loop._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)

    assert loop._message_seen("target user", "what time is it .detail", "fp-2")


def test_agent_loop_cleans_qq_quote_reply_to_bot_as_latest_line():
    loop = build_loop()
    loop.agent = agent_with_aliases("楠bot")
    loop._sent_texts = ["我看看"]
    raw = message("楠bot 不\n我看看。\n早上吃什么", "fp-quote", top=100)

    cleaned = loop._clean_visible_message(raw)

    assert cleaned.text == "早上吃什么"
    assert cleaned.turn.references_bot
    assert cleaned.turn.removed_lines == ("楠bot 不", "我看看。")


def test_agent_loop_deduplicates_quote_reply_when_raw_block_changes():
    loop = build_loop()
    loop.agent = agent_with_aliases("楠bot")
    loop._sent_texts = ["我看看"]
    raw_quote = message("楠bot 不\n我看看。\n早上吃什么", "fp-quote", top=100)
    refreshed_quote = message("我看看。\n早上吃什么", "fp-refreshed", top=120)

    enqueued = loop._enqueue_visible_targets([raw_quote])
    queued = enqueued[0]
    loop._pending_messages.popleft()
    loop._turn_ledger.mark_inflight(queued.identity)

    repeated = loop._enqueue_visible_targets([refreshed_quote])

    assert queued.text == "早上吃什么"
    assert loop._clean_visible_message(refreshed_quote).identity == queued.identity
    assert repeated == []


def test_agent_loop_prefers_clean_visible_message_over_quote_wrapper():
    loop = build_loop()
    loop.agent = agent_with_aliases("target user")
    wrapper = message(
        "old reply\ntarget user\nnanato! what work do you do",
        "fp-wrapper",
        top=100,
        sender_name="other user",
    )
    clean = message("nanato! what work do you do", "fp-clean", top=140, sender_name="target user")

    enqueued = loop._enqueue_visible_targets([wrapper, clean])

    assert [item.sender_name for item in enqueued] == ["target user"]
    assert enqueued[0].fingerprint == "fp-clean"


def test_agent_loop_skips_own_outgoing_quote_echo_from_target_queue():
    loop = build_loop()
    loop._sent_texts = ["yes, still here"]
    echo = message("nanato revive\nyes, still here", "fp-echo", top=100)

    enqueued = loop._enqueue_visible_targets([echo])

    assert enqueued == []
    assert loop._message_seen(echo.sender_name, "nanato revive\nyes, still here", echo.fingerprint)


def test_agent_loop_selects_oldest_unseen_message_first():
    loop = build_loop()
    older = message("older", "fp-1", top=100)
    latest = message("latest", "fp-2", top=200)

    selected = loop._next_unseen_messages([older, latest])

    assert selected == [older, latest]
    assert not loop._message_seen(older.sender_name, older.text, older.fingerprint)
    assert not loop._message_seen(latest.sender_name, latest.text, latest.fingerprint)


def test_agent_loop_limits_unseen_messages_per_tick():
    loop = build_loop(max_messages_per_tick=1)
    older = message("older", "fp-1", top=100)
    latest = message("latest", "fp-2", top=200)

    selected = loop._next_unseen_messages([older, latest])

    assert selected == [older]


def test_agent_loop_uses_passive_qq_reads():
    loop = build_loop()
    calls = []

    class QQ:
        def read_visible_context(self, *, passive=False):
            calls.append(passive)
            raise TimeoutError("stop after recording passive flag")

    loop.qq = QQ()

    try:
        import asyncio

        asyncio.run(loop._read_visible_context("test"))
    except TimeoutError:
        pass

    assert calls == [True]


def test_tick_does_not_read_or_consume_messages_when_not_armed():
    import asyncio

    loop = build_loop(dry_run=False)
    reads = []

    class Status:
        armed = False

        def to_dict(self):
            return {"armed": False, "dry_run": False}

    class QQ:
        def status(self):
            return Status()

        def read_visible_context(self, *, passive=False):
            reads.append(passive)
            raise AssertionError("disarmed loop should not read QQ")

    loop.qq = QQ()

    result = asyncio.run(loop.tick())

    assert result["reason"] == "qq_window_unavailable"
    assert reads == []
    assert loop.status()["ledger"]["record_count"] == 0


def test_agent_loop_records_other_visible_users_as_context_only():
    loop = build_loop()
    recorded = []

    class Store:
        def append_event(self, **kwargs):
            recorded.append(kwargs)

    loop.store = Store()

    loop._record_visible_context(
        [
            message("other text", "fp-other", top=100, sender_name="other user"),
            message("target text", "fp-target", top=140, sender_name="target user"),
            message("bot text", "fp-bot", top=180, sender_name="bot user"),
        ]
    )

    assert [item["source"] for item in recorded] == ["other user"]
    assert recorded[0]["metadata"]["agent_action"] == "context_only"


def test_agent_loop_initializes_target_and_other_contacts():
    loop = build_loop()
    calls = []

    class SocialState:
        def ensure_contact(self, **kwargs):
            calls.append(kwargs)

    class Agent:
        social_state = SocialState()

    loop.agent = Agent()
    loop._initialize_visible_contacts(
        [
            message("other text", "fp-other", top=100, sender_name="other user"),
            message("target text", "fp-target", top=140, sender_name="target user"),
        ]
    )

    assert calls == [
        {"user_name": "other user", "initial_affinity": 0.5, "source": "visible_contact_seed"},
        {"user_name": "target user", "initial_affinity": 1.0, "source": "target_contact_seed"},
    ]


def test_record_visible_read_initializes_contacts_and_context():
    loop = build_loop()
    events = []
    contacts = []

    class Store:
        def append_event(self, **kwargs):
            events.append(kwargs)

    class SocialState:
        def ensure_contact(self, **kwargs):
            contacts.append(kwargs)

    class Agent:
        social_state = SocialState()

    loop.store = Store()
    loop.agent = Agent()
    result = QQReadResult(
        active_group_name="target group",
        expected_group_name="target group",
        target_sender_name="target user",
        bot_sender_name="bot user",
        group_matched=True,
        visible_items=[],
        chat_messages=[
            message("other text", "fp-other", top=100, sender_name="other user"),
            message("target text", "fp-target", top=140, sender_name="target user"),
        ],
        target_messages=[],
    )

    metadata = loop.record_visible_read(result)

    assert metadata == {"contacts_seen": 2, "context_recorded": 1, "reason": "recorded"}
    assert [item["user_name"] for item in contacts] == ["other user", "target user"]
    assert [item["source"] for item in events] == ["other user"]


def test_tick_buffers_visible_target_messages_before_processing():
    import asyncio

    loop = build_loop(max_messages_per_tick=1)
    events = []
    first = message("first", "fp-first", top=100)
    second = message("second", "fp-second", top=150)

    class Store:
        def append_event(self, **kwargs):
            events.append(kwargs)

    class SocialState:
        def ensure_contact(self, **kwargs):
            pass

    class Agent:
        social_state = SocialState()

    class QQ:
        def read_visible_context(self, *, passive=False):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[first, second],
                target_messages=[first, second],
            )

    loop.store = Store()
    loop.agent = Agent()
    loop.qq = QQ()

    result = asyncio.run(loop.tick())

    assert result["pending_message_count"] == 0
    assert result["aggregating_message_count"] == 1
    assert result["new_observation_count"] == 2
    assert result["enqueued"] == []
    assert not loop._message_seen(first.sender_name, first.text, first.fingerprint)
    message_events = [event for event in events if event.get("kind") == "group_message"]
    assert [event["metadata"]["agent_action"] for event in message_events] == ["aggregating", "aggregating"]


def test_agent_loop_does_not_record_same_turn_when_buffer_flushes_to_queue():
    loop = build_loop()
    events = []

    class Store:
        def append_event(self, **kwargs):
            events.append(kwargs)

    loop.store = Store()

    incoming = message("you ok", "fp-visible", top=100)

    assert loop._enqueue_visible_targets([incoming], respect_quiet_period=True, now=1000.0) == []
    enqueued = loop._enqueue_visible_targets([], respect_quiet_period=True, now=1008.0)

    assert [item.text for item in enqueued] == ["you ok"]
    message_events = [event for event in events if event.get("kind") == "group_message"]
    assert len(message_events) == 1
    assert message_events[0]["metadata"]["agent_action"] == "aggregating"
    assert message_events[0]["metadata"]["clean_identity"] == "target user|you ok"


def test_agent_loop_hydrates_context_identity_from_recent_group_messages(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.append_event(
        source="target user",
        kind="group_message",
        content="you ok",
        metadata={
            "sender_name": "target user",
            "clean_text": "you ok",
            "clean_identity": "target user|you ok",
            "fingerprint": "fp-old",
            "raw_message_text": "you ok",
        },
    )

    loop = build_loop(store=store)
    event_count = len(store.recent_events(limit=20))

    loop._record_context_message(
        message("you ok", "fp-new-coordinate", top=150),
        agent_reason="queued_for_decision",
        agent_action="queued",
    )

    assert len(store.recent_events(limit=20)) == event_count
    assert loop._message_seen("target user", "you ok", "fp-new-coordinate")


def test_tick_buffers_non_target_visible_messages_for_gate_decision():
    import asyncio

    loop = build_loop(max_messages_per_tick=3)
    other = message("bot should maybe answer this", "fp-other", top=100, sender_name="other user")

    class Store:
        def append_event(self, **kwargs):
            pass

    class SocialState:
        def ensure_contact(self, **kwargs):
            pass

    class Agent:
        social_state = SocialState()

    class QQ:
        def read_visible_context(self, *, passive=False):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[other],
                target_messages=[],
            )

    loop.store = Store()
    loop.agent = Agent()
    loop.qq = QQ()

    result = asyncio.run(loop.tick())

    assert result["pending_message_count"] == 0
    assert result["aggregating_message_count"] == 1
    assert result["new_observation_count"] == 1
    assert result["enqueued"] == []


def test_startup_baseline_collects_scrollback_as_context_only(tmp_path):
    import asyncio

    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    loop = build_loop(store=store)
    old = message("old target context", "fp-old-target", top=100, sender_name="target user")
    other = message("other context", "fp-other", top=150, sender_name="other user")
    bot = message("bot context", "fp-bot", top=200, sender_name="bot user")

    class SocialState:
        def ensure_contact(self, **kwargs):
            pass

    class Agent:
        social_state = SocialState()

    class QQ:
        def read_scrollback_context(self, *, pages=3):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[old, other, bot],
                target_messages=[old],
            )

    loop.agent = Agent()
    loop.qq = QQ()

    result = asyncio.run(loop._mark_startup_baseline())

    assert result["reason"] == "startup_scrollback_marked"
    assert result["marked_count"] == 2
    assert loop._message_seen("target user", "old target context", "fp-old-target")
    assert loop._message_seen("other user", "other context", "fp-other")
    assert len(loop._pending_messages) == 0
    events = [event for event in store.recent_events() if event.kind == "group_message"]
    assert [event.content for event in events] == ["old target context", "other context"]
    assert {event.metadata["agent_reason"] for event in events} == {"startup_scrollback_context"}


def test_processor_handles_queued_messages_in_fifo_order():
    import asyncio

    loop = build_loop(max_messages_per_tick=1)
    replies = []
    record_flags = []
    first = message("first", "fp-first", top=100)
    second = message("second", "fp-second", top=150)

    class AgentResult:
        def __init__(self, reply):
            self.action = "reply"
            self.reply = reply
            self.reason = "model_reply"
            self.used_model = True
            self.metadata = {}

    class Agent:
        social_state = None

        async def respond_to_incoming(self, **kwargs):
            replies.append(kwargs["message"])
            record_flags.append(kwargs.get("record_incoming_event"))
            return AgentResult(f"reply to {kwargs['message']}")

    class Store:
        def append_event(self, **kwargs):
            pass

    class Result:
        def to_dict(self):
            return {"sent": True, "reason": "sent"}

    class QQ:
        def read_visible_context(self, *, passive=False):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[first, second],
                target_messages=[first, second],
            )

        def send_text(self, text, *, reply_to=None):
            return Result()

    loop.agent = Agent()
    loop.store = Store()
    loop.qq = QQ()
    loop._enqueue_visible_targets([first, second])

    first_decision = asyncio.run(loop._process_next_pending_message())
    second_decision = asyncio.run(loop._process_next_pending_message())

    assert replies == ["first", "second"]
    assert record_flags == [False, False]
    assert first_decision.message_text == "first"
    assert second_decision.message_text == "second"
    assert loop.status()["pending_message_count"] == 0
    assert loop._message_seen(first.sender_name, first.text, first.fingerprint)
    assert loop._message_seen(second.sender_name, second.text, second.fingerprint)


def test_processor_task_restarts_when_loop_is_still_running():
    import asyncio

    events = []

    class Store:
        def append_event(self, **kwargs):
            events.append(kwargs)

            class Event:
                id = len(events)

            return Event()

    async def finished_task():
        return None

    async def run():
        loop = build_loop(store=Store())
        old_task = asyncio.create_task(finished_task())
        await old_task

        loop._processor_task = old_task
        loop._ensure_processor_running("test")

        assert loop._processor_task is not old_task
        assert not loop._processor_task.done()
        assert events[-1]["kind"] == "loop_processor_started"

        loop._stop_requested = True
        loop._processor_wakeup.set()
        loop._processor_task.cancel()
        try:
            await loop._processor_task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())


def test_placeholder_send_uses_qq_quote_reply_target():
    import asyncio

    loop = build_loop()
    calls = []

    class QQ:
        def read_visible_context(self, *, passive=False):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[refreshed],
                target_messages=[refreshed],
            )

        def send_text(self, text, *, reply_to=None):
            calls.append({"text": text, "reply_to": reply_to})

            class Result:
                def to_dict(self):
                    return {"sent": True, "reason": "sent"}

            return Result()

    loop.qq = QQ()
    target = message("please check", "fp-target", top=140, sender_name="target user")
    refreshed = message("please check", "fp-target", top=180, sender_name="target user")

    result = asyncio.run(loop._send_placeholder(message=target, placeholder="等我一下"))

    assert result["sent"]
    assert result["reason"] == "sent"
    assert result["verification"]["quote_refresh"]["reason"] == "fingerprint_match"
    assert calls == [{"text": "等我一下", "reply_to": refreshed}]


def test_placeholder_send_is_once_per_clean_message_identity():
    import asyncio

    loop = build_loop()
    calls = []
    target = message("please check", "fp-target", top=140, sender_name="target user")

    class QQ:
        def read_visible_context(self, *, passive=False):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[target],
                target_messages=[target],
            )

        def send_text(self, text, *, reply_to=None):
            calls.append({"text": text, "reply_to": reply_to})

            class Result:
                def to_dict(self):
                    return {"sent": True, "reason": "sent"}

            return Result()

    loop.qq = QQ()

    first = asyncio.run(loop._send_placeholder(message=target, placeholder="One moment"))
    second = asyncio.run(loop._send_placeholder(message=target, placeholder="One moment"))

    assert first["sent"]
    assert second["sent"] is False
    assert second["reason"] == "placeholder_already_sent_for_message"
    assert len(calls) == 1


def test_final_reply_after_placeholder_sends_unquoted_followup():
    import asyncio

    loop = build_loop()
    calls = []
    events = []
    target = message("look this up", "fp-target", top=140, sender_name="target user")

    class Result:
        def to_dict(self):
            return {"sent": True, "reason": "sent", "verification": {}}

    class QQ:
        def read_visible_context(self, *, passive=False):
            raise AssertionError("follow-up final send should not refresh the old quote target")

        def send_text(self, text, *, reply_to=None):
            calls.append({"text": text, "reply_to": reply_to})
            return Result()

    class AgentResult:
        action = "reply"
        reply = "final answer"
        reason = "model_reply"
        used_model = True
        metadata = {"placeholder_sent": True}

    class Agent:
        async def respond_to_incoming(self, **kwargs):
            return AgentResult()

    class Store:
        def append_event(self, **kwargs):
            events.append(kwargs)

    loop.qq = QQ()
    loop.agent = Agent()
    loop.store = Store()

    decision = asyncio.run(loop._handle_message(target, 0.0))

    assert decision.sent
    assert calls == [{"text": "final answer", "reply_to": None}]
    assert decision.metadata["send_result"]["verification"]["stage"] == "final_followup"
    assert decision.metadata["send_result"]["verification"]["mode"] == "followup_unquoted"


def test_final_answer_is_once_per_clean_turn():
    import asyncio

    loop = build_loop()
    calls = []
    target = message("nanato today food", "fp-target", top=140, sender_name="target user")

    class Result:
        def to_dict(self):
            return {"sent": True, "reason": "sent", "verification": {}}

    class QQ:
        def read_visible_context(self, *, passive=False):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[target],
                target_messages=[target],
            )

        def send_text(self, text, *, reply_to=None):
            calls.append({"text": text, "reply_to": reply_to})
            return Result()

    class AgentResult:
        action = "reply"
        reply = "one answer"
        reason = "model_reply"
        used_model = True
        metadata = {}

    class Agent:
        async def respond_to_incoming(self, **kwargs):
            return AgentResult()

    class Store:
        def append_event(self, **kwargs):
            pass

    loop.qq = QQ()
    loop.agent = Agent()
    loop.store = Store()

    first = asyncio.run(loop._handle_message(target, 0.0))
    second = asyncio.run(loop._handle_message(target, 0.0))

    assert first.sent
    assert not second.sent
    assert second.send_reason == "answer_already_attempted_for_message"
    assert calls == [{"text": "one answer", "reply_to": target}]


def test_quoted_send_refuses_when_target_is_not_visible():
    import asyncio

    loop = build_loop()
    calls = []

    class QQ:
        def read_visible_context(self, *, passive=False):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[],
                target_messages=[],
            )

        def send_text(self, text, *, reply_to=None):
            calls.append({"text": text, "reply_to": reply_to})
            raise AssertionError("send_text should not be called without a quote target")

    loop.qq = QQ()
    target = message("please check", "fp-target", top=140, sender_name="target user")

    result = asyncio.run(loop._send_quoted_text(message=target, text="reply", stage="final_reply"))

    assert result["sent"] is False
    assert result["reason"] == "quote_target_not_visible"
    assert calls == []


def test_final_reply_can_fallback_to_unquoted_when_quote_target_is_missing():
    import asyncio

    loop = build_loop()
    calls = []

    class Result:
        def to_dict(self):
            return {"sent": True, "reason": "sent", "verification": {}}

    class QQ:
        def read_visible_context(self, *, passive=False):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[],
                target_messages=[],
            )

        def send_text(self, text, *, reply_to=None):
            calls.append({"text": text, "reply_to": reply_to})
            return Result()

    loop.qq = QQ()
    target = message("please check", "fp-target", top=140, sender_name="target user")

    result = asyncio.run(
        loop._send_quoted_text(
            message=target,
            text="reply",
            stage="final_reply",
            allow_unquoted_fallback=True,
        )
    )

    assert result["sent"]
    assert calls == [{"text": "reply", "reply_to": None}]
    assert result["verification"]["mode"] == "quote_fallback_unquoted"
    assert result["verification"]["quote_fallback"] == "unquoted_after_missing_quote_target"


def test_final_reply_can_fallback_to_unquoted_when_quote_send_fails():
    import asyncio

    loop = build_loop()
    calls = []
    target = message("please check", "fp-target", top=140, sender_name="target user")

    class QuoteFailure:
        def to_dict(self):
            return {"sent": False, "reason": "quote_failed", "verification": {"reason": "quote_menu_item_not_found"}}

    class Success:
        def to_dict(self):
            return {"sent": True, "reason": "sent", "verification": {}}

    class QQ:
        def read_visible_context(self, *, passive=False):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[target],
                target_messages=[target],
            )

        def send_text(self, text, *, reply_to=None):
            calls.append({"text": text, "reply_to": reply_to})
            return QuoteFailure() if reply_to is not None else Success()

    loop.qq = QQ()

    result = asyncio.run(
        loop._send_quoted_text(
            message=target,
            text="reply",
            stage="final_reply",
            allow_unquoted_fallback=True,
        )
    )

    assert result["sent"]
    assert calls == [{"text": "reply", "reply_to": target}, {"text": "reply", "reply_to": None}]
    assert result["verification"]["mode"] == "quote_fallback_unquoted"
    assert result["verification"]["quote_fallback"] == "unquoted_after_quote_send_failed"
    assert result["verification"]["quote_send_result"]["reason"] == "quote_failed"


def test_quote_refresh_matches_clean_identity_when_raw_block_changes():
    import asyncio

    loop = build_loop()
    original = message("old bot reply\n[debug elapsed=10s, prompt_tokens=99]\nwhat time is it .detail", "fp-original", top=140)
    refreshed = message("what time is it .detail", "fp-refreshed", top=180)

    class QQ:
        def read_visible_context(self, *, passive=False):
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[refreshed],
                target_messages=[refreshed],
            )

    loop.qq = QQ()

    target, metadata = asyncio.run(loop._fresh_quote_target_unlocked(loop._clean_visible_message(original)))

    assert target == refreshed
    assert metadata["reason"] == "clean_identity_match"


def test_reboot_is_scheduled_after_successful_send():
    import asyncio

    loop = build_loop()
    schedules = []
    events = []

    class Result:
        def to_dict(self):
            return {"sent": True, "reason": "sent"}

    class QQ:
        def read_visible_context(self, *, passive=False):
            target = message(".reboot", "fp-reboot", top=180)
            return QQReadResult(
                active_group_name="target group",
                expected_group_name="target group",
                target_sender_name="target user",
                bot_sender_name="bot user",
                group_matched=True,
                visible_items=[],
                chat_messages=[target],
                target_messages=[target],
            )

        def send_text(self, text, *, reply_to=None):
            return Result()

    class AgentResult:
        action = "reply"
        reply = "Reboot scheduled."
        reason = "reboot_requested"
        used_model = False
        metadata = {"reboot_requested": True}

    class Agent:
        async def respond_to_incoming(self, **kwargs):
            return AgentResult()

    class Store:
        def append_event(self, **kwargs):
            events.append(kwargs)

    loop.qq = QQ()
    loop.agent = Agent()
    loop.store = Store()
    loop.reboot_scheduler = lambda reason: schedules.append(reason) or {"scheduled": True, "reason": reason}

    decision = asyncio.run(loop._handle_message(message(".reboot", "fp-reboot", top=140), 0.0))

    assert decision.sent
    assert schedules == ["qq_command"]
    assert decision.metadata["reboot_schedule"]["scheduled"]
    assert any(event["kind"] == "reboot_scheduled" for event in events)


def test_agent_loop_marks_configured_bot_alias_quote_as_direct_reply():
    loop = build_loop(bot_sender_aliases=("楠bot",))
    raw = message("楠bot\n嗯……发呆呢，你呢？\n我在吃晚饭，一会去上班 .detail", "fp-real-quote", top=100)

    cleaned = loop._clean_visible_message(raw)

    assert cleaned.text == "我在吃晚饭，一会去上班 .detail"
    assert cleaned.turn.references_bot
    assert cleaned.turn.removed_lines == ("楠bot", "嗯……发呆呢，你呢？")


def test_agent_loop_filters_visible_messages_from_configured_bot_alias():
    loop = build_loop(bot_sender_aliases=("楠bot",))
    own_message = message("嗯……在看雨。", "fp-own", top=100, sender_name="楠bot")

    enqueued = loop._enqueue_visible_targets([own_message])

    assert enqueued == []
    assert loop._message_seen("楠bot", "嗯……在看雨。", "fp-own")


def test_agent_loop_blocks_low_value_spontaneous_topics():
    loop = build_loop()

    low_value = loop._spontaneous_topic_check("今天挺安静的……")
    useful_question = loop._spontaneous_topic_check("今天有人吃饭了吗？")

    assert not low_value["ok"]
    assert low_value["reason"] == "low_value_idle_observation"
    assert useful_question["ok"]


def test_agent_loop_merges_plain_quick_messages_from_same_sender():
    loop = build_loop()

    loop._enqueue_visible_targets([message("A", "fp-a", top=100)], respect_quiet_period=True, now=1000.0)
    loop._enqueue_visible_targets([message("B", "fp-b", top=140)], respect_quiet_period=True, now=1001.0)
    ready = loop._flush_ready_turn_groups(now=1008.0)

    assert [item.text for item in ready] == ["A\nB"]


def test_agent_loop_does_not_merge_ignore_segment_with_following_message():
    loop = build_loop()

    enqueued = loop._enqueue_visible_targets([message("A.i", "fp-a", top=100)], respect_quiet_period=True, now=1000.0)
    loop._enqueue_visible_targets([message("B", "fp-b", top=140)], respect_quiet_period=True, now=1001.0)
    ready = loop._flush_ready_turn_groups(now=1008.0)

    assert [item.text for item in enqueued] == ["A.i"]
    assert [item.text for item in ready] == ["B"]


def test_agent_loop_cleans_quote_block_before_queueing():
    loop = build_loop()
    loop.agent = agent_with_aliases("Tsubashimo Nanato")
    raw = message(
        "陳丷\n@Tsubashimo Nanato\n真得掐你脖子了\n哦对了你叫我也会激活她，因为是蒸馏的我自己 .i",
        "fp-quote-block",
        top=100,
    )

    cleaned = loop._clean_visible_message(raw)

    assert cleaned.text == "哦对了你叫我也会激活她，因为是蒸馏的我自己 .i"
    assert cleaned.references_bot
    assert cleaned.turn.reason in {"quote_prefix_removed", "noise_removed_latest_line"}


def test_manual_force_duplicate_does_not_call_agent_twice(tmp_path):
    import asyncio

    class AgentResult:
        action = "reply"
        reply = "reply"
        reason = "model"
        metadata = {}

    class Agent:
        def __init__(self):
            self.calls = 0

        async def respond_to_incoming(self, **kwargs):
            self.calls += 1
            return AgentResult()

    loop = build_loop(store=SQLiteMemoryStore(tmp_path / "memory.sqlite3"))
    agent = Agent()
    loop.agent = agent

    first = asyncio.run(
        loop.force_reply(
            sender_name="target user",
            message_text="hello",
            event_id=123,
            send_to_qq=False,
        )
    )
    second = asyncio.run(
        loop.force_reply(
            sender_name="target user",
            message_text="hello",
            event_id=123,
            send_to_qq=False,
        )
    )

    assert first["action"] == "reply"
    assert second["reason"] == "manual_force_recent_duplicate"
    assert second["sent"] is False
    assert agent.calls == 1


def build_loop(
    *,
    dry_run: bool = True,
    max_messages_per_tick: int = 2,
    idle_poll_interval_seconds: float = 5.0,
    idle_poll_after_ticks: int = 3,
    store=None,
    bot_sender_aliases: tuple[str, ...] = (),
) -> AgentLoop:
    return AgentLoop(
        agent=None,
        qq=None,
        store=store,
        config=QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="target user",
            bot_sender_name="bot user",
            dry_run=dry_run,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=6,
            probe_max_children=100,
            poll_interval_seconds=1.0,
            max_messages_per_tick=max_messages_per_tick,
            ignore_existing_on_start=True,
            idle_poll_interval_seconds=idle_poll_interval_seconds,
            idle_poll_after_ticks=idle_poll_after_ticks,
            bot_sender_aliases=bot_sender_aliases,
        ),
    )


def message(text: str, fingerprint: str, top: int, sender_name: str = "target user") -> QQChatMessage:
    return QQChatMessage(
        sender_name=sender_name,
        text=text,
        fingerprint=fingerprint,
        rectangle={"left": 100, "top": top, "right": 200, "bottom": top + 40},
    )


def agent_with_aliases(*aliases: str):
    class Guard:
        reply_aliases = aliases

    class Agent:
        persona_guard = Guard()

    return Agent()
