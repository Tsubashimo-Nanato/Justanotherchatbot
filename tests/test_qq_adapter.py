from local_qq_agent.config import QQConfig
from local_qq_agent.qq import QQWindowAdapter


class FakeWindow:
    def window_text(self):
        return "QQ"


class GuardedQQWindowAdapter(QQWindowAdapter):
    def __init__(self, config, active_group_name):
        super().__init__(config)
        self._test_active_group_name = active_group_name

    def _find_window(self):
        return FakeWindow()

    def _active_group_name(self, window):
        return self._test_active_group_name


class TitleWindow:
    def __init__(self, title, *, visible=True, minimized=False):
        self._title = title
        self._visible = visible
        self._minimized = minimized

    def window_text(self):
        return self._title

    def is_visible(self):
        return self._visible

    def is_minimized(self):
        return self._minimized

    def rectangle(self):
        class Rect:
            left = 10
            top = 20
            right = 610
            bottom = 720

        return Rect()


class InteractionWindow(TitleWindow):
    def __init__(self, title, *, minimized=False):
        super().__init__(title, minimized=minimized)
        self.restored = 0
        self.focused = 0
        self.minimized_count = 0

    def restore(self):
        self.restored += 1

    def set_focus(self):
        self.focused += 1

    def minimize(self):
        self.minimized_count += 1


class PassiveReadAdapter(QQWindowAdapter):
    def __init__(self, config, window):
        super().__init__(config)
        self.window = window
        self.scrolled = 0

    def _find_window(self):
        return self.window

    def _scroll_to_latest(self, window):
        self.scrolled += 1

    def _control_entries(self, window):
        return []


def test_qq_send_is_blocked_when_not_armed():
    adapter = QQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="",
            target_sender_name="target user",
            bot_sender_name="bot user",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=1,
            probe_max_children=10,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        )
    )

    result = adapter.send_text("hello")

    assert not result.sent
    assert result.reason == "not_armed"


def test_qq_send_dry_run_after_arm():
    adapter = QQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="",
            target_sender_name="target user",
            bot_sender_name="bot user",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=1,
            probe_max_children=10,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        )
    )

    adapter.arm()
    result = adapter.send_text("hello")

    assert not result.sent
    assert result.dry_run
    assert result.reason == "dry_run"


def test_qq_send_blocks_wrong_group_after_arm():
    adapter = GuardedQQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="target user",
            bot_sender_name="bot user",
            dry_run=False,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=1,
            probe_max_children=10,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        ),
        active_group_name="other group",
    )

    adapter.arm()
    result = adapter.send_text("hello")

    assert not result.sent
    assert result.reason == "wrong_group"
    assert result.verification["expected_group_name"] == "target group"
    assert result.verification["active_group_name"] == "other group"


def test_qq_send_requires_expected_group_for_real_send():
    adapter = GuardedQQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="",
            target_sender_name="target user",
            bot_sender_name="bot user",
            dry_run=False,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=1,
            probe_max_children=10,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        ),
        active_group_name="target group",
    )

    adapter.arm()
    result = adapter.send_text("hello")

    assert not result.sent
    assert result.reason == "expected_group_missing"


def test_quote_click_point_prefers_message_content_start():
    adapter = QQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="target user",
            bot_sender_name="bot user",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=1,
            probe_max_children=10,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        )
    )

    rectangle = {"left": 100, "top": 120, "right": 220, "bottom": 180}

    assert adapter._quote_click_point(rectangle) == (130, 150)
    assert adapter._quote_click_points(rectangle) == [(130, 150), (118, 150), (160, 150), (130, 140)]
    assert adapter._quote_click_point({"left": 100, "top": 120, "right": 80, "bottom": 180}) is None


def test_quote_click_points_deduplicate_small_rectangles():
    adapter = QQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="target user",
            bot_sender_name="bot user",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=1,
            probe_max_children=10,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        )
    )

    points = adapter._quote_click_points({"left": 100, "top": 120, "right": 112, "bottom": 132})

    assert len(points) == len(set(points))
    assert points[0] == (104, 126)


def test_popout_group_title_is_preferred_over_main_qq_window():
    adapter = QQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="target user",
            bot_sender_name="bot user",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=1,
            probe_max_children=10,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        )
    )

    popout_score = adapter._window_candidate_score(TitleWindow("target group"))
    main_score = adapter._window_candidate_score(TitleWindow("QQ", minimized=True))

    assert popout_score > main_score
    assert adapter._active_group_name_from_entries(TitleWindow("target group"), []) == "target group"


def test_popout_message_rect_uses_conversation_layout():
    adapter = QQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="target user",
            bot_sender_name="bot user",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=1,
            probe_max_children=10,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        )
    )

    rect = adapter._message_list_rect(TitleWindow("target group"), [])

    assert rect == {"left": 26, "top": 102, "right": 594, "bottom": 570}


def test_passive_read_does_not_focus_restore_or_scroll():
    window = InteractionWindow("target group", minimized=True)
    adapter = PassiveReadAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="target user",
            bot_sender_name="bot user",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=1,
            probe_max_children=10,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        ),
        window,
    )

    result = adapter.read_visible_context(passive=True)

    assert result.group_matched
    assert window.restored == 0
    assert window.focused == 0
    assert window.minimized_count == 0
    assert adapter.scrolled == 0


def test_visible_chat_items_ignore_member_list_target_name():
    adapter = QQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="Target User",
            bot_sender_name="Bot User",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=6,
            probe_max_children=100,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        )
    )
    entries = [
        entry("消息列表", "Window", 100, 100, 500, 400),
        entry("Target User", "Text", 620, 120, 760, 140),
        entry("Target User", "Group", 104, 141, 136, 173),
        entry("Target User", "Text", 144, 140, 284, 156),
        entry("群主", "Text", 270, 140, 310, 156),
        entry("hello #d", "Text", 164, 164, 264, 190),
    ]

    visible_items = adapter._visible_chat_items(FakeWindow(), entries)
    messages = adapter._target_chat_messages(visible_items)

    assert all(item["rectangle"]["right"] <= 500 for item in visible_items)
    assert len(messages) == 1
    assert messages[0].sender_name == "Target User"
    assert messages[0].text == "hello #d"


def test_target_messages_stop_before_bot_sender_block():
    adapter = QQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="Target User",
            bot_sender_name="Bot User",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=6,
            probe_max_children=100,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        )
    )
    visible_items = [
        visible_item("Target User", "Text", 120, 100, 260, 116),
        visible_item("Target User", "Group", 80, 101, 112, 133),
        visible_item("hello", "Text", 140, 130, 240, 150),
        visible_item("Bot User", "Text", 600, 170, 680, 186),
        visible_item("Bot User", "Group", 690, 171, 722, 203),
        visible_item("bot reply should be ignored", "Text", 360, 200, 560, 224),
    ]

    messages = adapter._target_chat_messages(visible_items)

    assert [message.text for message in messages] == ["hello"]


def test_target_messages_ignore_right_side_text_without_sender_label():
    adapter = QQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="Target User",
            bot_sender_name="Bot User",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=6,
            probe_max_children=100,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        )
    )
    visible_items = [
        visible_item("Target User", "Text", 120, 100, 260, 116),
        visible_item("Target User", "Group", 80, 101, 112, 133),
        visible_item("hello", "Text", 140, 130, 240, 150),
        visible_item("bot reply without visible sender label", "Text", 340, 165, 560, 188),
    ]

    messages = adapter._target_chat_messages(visible_items)

    assert [message.text for message in messages] == ["hello"]


def test_chat_messages_include_multiple_visible_senders():
    adapter = QQWindowAdapter(
        QQConfig(
            window_title_regex="QQ",
            expected_group_name="target group",
            target_sender_name="Target User",
            bot_sender_name="Bot User",
            dry_run=True,
            send_requires_armed=True,
            verify_after_send=True,
            probe_max_depth=6,
            probe_max_children=100,
            poll_interval_seconds=1.0,
            max_messages_per_tick=2,
            ignore_existing_on_start=True,
        )
    )
    visible_items = [
        visible_item("Other User", "Text", 120, 100, 260, 116),
        visible_item("Other User", "Group", 80, 101, 112, 133),
        visible_item("side comment", "Text", 140, 130, 240, 150),
        visible_item("Target User", "Text", 120, 180, 260, 196),
        visible_item("Target User", "Group", 80, 181, 112, 213),
        visible_item("direct comment", "Text", 140, 210, 260, 230),
    ]

    messages = adapter._chat_messages(visible_items)
    target_messages = adapter._target_chat_messages(visible_items)

    assert [(message.sender_name, message.text) for message in messages] == [
        ("Other User", "side comment"),
        ("Target User", "direct comment"),
    ]
    assert [(message.sender_name, message.text) for message in target_messages] == [
        ("Target User", "direct comment"),
    ]


def entry(name, control_type, left, top, right, bottom):
    return {
        "depth": 0,
        "name": name,
        "class_name": "",
        "control_type": control_type,
        "rectangle": {"left": left, "top": top, "right": right, "bottom": bottom},
    }


def visible_item(text, control_type, left, top, right, bottom):
    return {
        "text": text,
        "control_type": control_type,
        "rectangle": {"left": left, "top": top, "right": right, "bottom": bottom},
    }
