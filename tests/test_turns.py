from local_qq_agent.agent.turns import clean_turn_text


def test_clean_turn_uses_latest_line_after_qq_quote_block():
    turn = clean_turn_text(
        "陳丷\n@Tsubashimo Nanato\n真得掐你脖子了\n哦对了你叫我也会激活她，因为是蒸馏的我自己 .i",
        quote_sender_names=("Tsubashimo Nanato",),
    )

    assert turn.text == "哦对了你叫我也会激活她，因为是蒸馏的我自己 .i"
    assert turn.reason in {"quote_prefix_removed", "noise_removed_latest_line"}
    assert turn.references_bot
    assert set(turn.removed_lines) == {"陳丷", "@Tsubashimo Nanato", "真得掐你脖子了"}
    assert turn.segments[-1] == {"kind": "current", "text": "哦对了你叫我也会激活她，因为是蒸馏的我自己 .i"}


def test_clean_turn_uses_latest_line_after_bot_quote():
    turn = clean_turn_text(
        "楠bot\n嗯\n早上吃点什么",
        recent_bot_texts=("嗯",),
        quote_sender_names=("楠bot",),
    )

    assert turn.text == "早上吃点什么"
    assert turn.references_bot
    assert turn.removed_lines == ("楠bot", "嗯")


def test_clean_turn_removes_recent_bot_notice_prefix():
    turn = clean_turn_text(
        "QQ armed 用python字符打印高度为5的圣诞树",
        recent_bot_texts=("QQ armed",),
    )

    assert turn.text == "用python字符打印高度为5的圣诞树"
    assert turn.reason == "recent_bot_prefix_removed"
    assert turn.references_bot
    assert turn.removed_lines == ("QQ armed",)


def test_clean_turn_does_not_merge_command_prefixed_line_into_current_turn():
    turn = clean_turn_text("grok是真的喜欢用黄豆 .i\n你。")

    assert turn.text == "你。"
    assert turn.reason == "command_prefix_removed"
    assert turn.removed_lines == ("grok是真的喜欢用黄豆 .i",)


def test_clean_turn_keeps_plain_multiline_message():
    turn = clean_turn_text("第一句\n第二句")

    assert turn.text == "第一句\n第二句"
    assert turn.reason == "unchanged"
    assert turn.removed_lines == ()
