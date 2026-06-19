from local_qq_agent.agent.commands import parse_message_commands


def test_parse_enforced_dot_suffix():
    parsed = parse_message_commands("reply to this .enforce")

    assert parsed.content == "reply to this"
    assert parsed.enforced
    assert not parsed.debug_requested
    assert not parsed.ignored
    assert parsed.thinking_level is None
    assert parsed.command_suffixes == (".enforce",)


def test_parse_detail_suffix_without_forcing_reply():
    parsed = parse_message_commands("status please .detail")

    assert parsed.content == "status please"
    assert not parsed.enforced
    assert parsed.debug_requested
    assert not parsed.ignored
    assert parsed.command_suffixes == (".detail",)


def test_parse_debug_suffix_without_forcing_reply():
    parsed = parse_message_commands("status please .debug")

    assert parsed.content == "status please"
    assert not parsed.enforced
    assert not parsed.debug_requested
    assert parsed.diagnostic_requested
    assert not parsed.ignored
    assert parsed.command_suffixes == (".debug",)


def test_parse_combined_suffixes_out_of_order():
    parsed = parse_message_commands("hello .detail .debug .think 2 .enforce")

    assert parsed.content == "hello"
    assert parsed.enforced
    assert parsed.debug_requested
    assert parsed.diagnostic_requested
    assert not parsed.ignored
    assert parsed.thinking_level == 2
    assert parsed.command_suffixes == (".detail", ".debug", ".think 2", ".enforce")


def test_parse_think_without_level_defaults_to_one():
    parsed = parse_message_commands("hello .think")

    assert parsed.content == "hello"
    assert parsed.thinking_level == 1
    assert parsed.command_suffixes == (".think",)


def test_parse_think_zero():
    parsed = parse_message_commands("hello .think 0")

    assert parsed.content == "hello"
    assert parsed.thinking_level == 0
    assert parsed.command_suffixes == (".think 0",)


def test_mid_sentence_think_is_plain_text():
    parsed = parse_message_commands("正文里 .think 2 不是后缀")

    assert parsed.content == "正文里 .think 2 不是后缀"
    assert parsed.thinking_level is None
    assert parsed.command_suffixes == ()


def test_help_is_standalone_command():
    parsed = parse_message_commands(".help")

    assert parsed.help_requested
    assert parsed.content == ""
    assert parsed.command_suffixes == (".help",)


def test_help_after_qq_quote_merge_is_standalone_command():
    parsed = parse_message_commands("楠bot\n14点37分。\n.help")

    assert parsed.help_requested
    assert parsed.content == ""
    assert parsed.command_suffixes == (".help",)


def test_status_is_standalone_command():
    parsed = parse_message_commands(".status")

    assert parsed.status_requested
    assert parsed.content == ""
    assert parsed.command_suffixes == (".status",)


def test_reboot_is_standalone_command():
    parsed = parse_message_commands(".reboot")

    assert parsed.reboot_requested
    assert parsed.content == ""
    assert parsed.command_suffixes == (".reboot",)


def test_debug_is_standalone_command():
    parsed = parse_message_commands(".debug")

    assert parsed.diagnostic_requested
    assert parsed.content == ""
    assert parsed.command_suffixes == (".debug",)


def test_status_suffix_is_plain_text():
    parsed = parse_message_commands("show this .status")

    assert parsed.content == "show this .status"
    assert not parsed.status_requested


def test_status_after_qq_quote_merge_is_standalone_command():
    parsed = parse_message_commands("quoted old reply\n.status")

    assert parsed.status_requested
    assert parsed.content == ""
    assert parsed.command_suffixes == (".status",)


def test_parse_set_think_and_activity():
    parsed = parse_message_commands(".set .think 0 .activity 0.25")

    assert parsed.set_requested
    assert parsed.setting_updates == {"default_thinking_level": 0, "activity": 0.25}
    assert parsed.setting_errors == ()


def test_parse_set_after_qq_quote_merge():
    parsed = parse_message_commands("quoted old reply\n.set .think 0 .activity 0.25")

    assert parsed.set_requested
    assert parsed.content == ""
    assert parsed.setting_updates == {"default_thinking_level": 0, "activity": 0.25}
    assert parsed.setting_errors == ()


def test_parse_set_rejects_invalid_activity():
    parsed = parse_message_commands(".set .activity 2")

    assert parsed.set_requested
    assert parsed.setting_updates == {}
    assert parsed.setting_errors == (".activity must be from 0 to 1, got 2",)


def test_parse_score_feedback_command():
    parsed = parse_message_commands(".score 0.3 打断")

    assert parsed.score_requested
    assert parsed.score_value == 0.3
    assert parsed.score_note == "打断"
    assert parsed.command_suffixes == (".score", "0.3", "打断")


def test_parse_compact_score_feedback_command():
    parsed = parse_message_commands(".score0.7 tone")

    assert parsed.score_requested
    assert parsed.score_value == 0.7
    assert parsed.score_note == "tone"


def test_parse_score_rejects_out_of_range_value():
    parsed = parse_message_commands(".score 1.5")

    assert parsed.score_requested
    assert parsed.score_value == 1.5
    assert parsed.setting_errors == (".score must be from 0 to 1, got 1.5",)


def test_old_hash_commands_are_plain_text():
    parsed = parse_message_commands("hello #e #d #i")

    assert parsed.content == "hello #e #d #i"
    assert not parsed.enforced
    assert not parsed.debug_requested
    assert not parsed.ignored
