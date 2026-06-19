from local_qq_agent.config import QQConfig


def test_qq_config_loads_local_override(tmp_path):
    config_path = tmp_path / "qq.yaml"
    local_path = tmp_path / "qq.local.yaml"
    config_path.write_text(
        "\n".join(
            [
                'window_title_regex: "QQ"',
                'expected_group_name: "CHANGE_ME"',
                'target_sender_name: "CHANGE_ME_TARGET"',
                'bot_sender_name: "CHANGE_ME_BOT"',
                "dry_run: true",
                "send_requires_armed: true",
                "verify_after_send: true",
                "probe_max_depth: 6",
                "probe_max_children: 450",
                "poll_interval_seconds: 1.0",
                "idle_poll_interval_seconds: 5.0",
                "idle_poll_after_ticks: 3",
                "max_messages_per_tick: 1",
                "ignore_existing_on_start: true",
            ]
        ),
        encoding="utf-8",
    )
    local_path.write_text(
        "\n".join(
            [
                'expected_group_name: "local group"',
                'target_sender_name: "local user"',
                'bot_sender_name: "local bot"',
                "bot_sender_aliases:",
                '  - "alias bot"',
                "dry_run: false",
            ]
        ),
        encoding="utf-8",
    )

    config = QQConfig.load(config_path)

    assert config.expected_group_name == "local group"
    assert config.target_sender_name == "local user"
    assert config.bot_sender_name == "local bot"
    assert config.bot_sender_aliases == ("alias bot",)
    assert config.dry_run is False
