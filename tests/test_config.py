from local_qq_agent.config import OneBotConfig


def test_onebot_config_loads_local_override(tmp_path):
    config_path = tmp_path / "onebot.yaml"
    local_path = tmp_path / "onebot.local.yaml"
    config_path.write_text(
        '\n'.join(
            [
                'reverse_ws_path: "/onebot/v11/ws"',
                'target_group_id: ""',
                'target_group_name: "CHANGE_ME"',
                'target_sender_name: "CHANGE_ME_TARGET"',
                'bot_sender_name: "CHANGE_ME_BOT"',
                'max_messages_per_tick: 4',
                'ignore_existing_on_start: true',
            ]
        ),
        encoding="utf-8",
    )
    local_path.write_text(
        '\n'.join(
            [
                'target_group_id: "123456"',
                'target_group_name: "local group"',
                'target_sender_name: "local user"',
                'bot_sender_name: "local bot"',
                'bot_sender_aliases:',
                '  - "alias bot"',
            ]
        ),
        encoding="utf-8",
    )

    config = OneBotConfig.load(config_path)

    assert config.target_group_id == "123456"
    assert config.target_group_name == "local group"
    assert config.target_sender_name == "local user"
    assert config.bot_sender_aliases == ("alias bot",)
