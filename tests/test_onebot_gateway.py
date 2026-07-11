import asyncio

from local_qq_agent.config import OneBotConfig
from local_qq_agent.onebot import OneBotGateway, OneBotMessage


def config() -> OneBotConfig:
    return OneBotConfig(
        reverse_ws_path="/onebot/v11/ws",
        access_token="secret",
        target_group_id="200",
        target_group_name="target",
        target_sender_name="owner",
        bot_sender_name="bot",
        max_messages_per_tick=4,
        ignore_existing_on_start=True,
    )


def event(*, message_id="300", user_id="400", post_type="message"):
    return {
        "time": 1_700_000_000,
        "post_type": post_type,
        "message_type": "group",
        "message_id": message_id,
        "self_id": "100",
        "group_id": "200",
        "user_id": user_id,
        "sender": {"card": "owner", "nickname": "fallback"},
        "message": [
            {"type": "reply", "data": {"id": "250"}},
            {"type": "at", "data": {"qq": "100"}},
            {"type": "text", "data": {"text": "hello"}},
        ],
    }


def test_group_event_has_stable_platform_identity_and_reply_metadata():
    gateway = OneBotGateway(config())
    gateway._self_id = "100"

    message = gateway._parse_group_message(event(), source="event")

    assert message is not None
    assert message.canonical_turn_id == "onebot:100:300"
    assert message.sender_name == "owner"
    assert message.text == "hello"
    assert message.reply_to_message_id == "250"
    assert message.mentions_self is True
    assert message.references_bot is True


def test_message_sent_event_is_self_echo():
    gateway = OneBotGateway(config())
    gateway._self_id = "100"

    message = gateway._parse_group_message(
        event(message_id="301", user_id="100", post_type="message_sent"),
        source="event",
    )

    assert message is not None
    assert message.is_self is True


def test_send_uses_reply_segment_and_returns_platform_message_id():
    async def scenario():
        gateway = OneBotGateway(config())
        gateway._self_id = "100"
        gateway._group_resolved = True
        socket = ActionSocket(gateway)
        gateway._socket = socket
        target = OneBotMessage(
            message_id="300",
            self_id="100",
            group_id="200",
            user_id="400",
            sender_name="owner",
            text="hello",
            timestamp=1,
        )

        result = await gateway.send_text("reply", reply_to=target)

        assert result.sent is True
        assert result.message_id == "900"
        segments = socket.requests[0]["params"]["message"]
        assert segments[0] == {"type": "reply", "data": {"id": "300"}}
        assert segments[1] == {"type": "text", "data": {"text": "reply"}}

    asyncio.run(scenario())


def test_send_timeout_is_unknown_and_is_not_retried():
    async def scenario():
        runtime_config = config()
        runtime_config = type(runtime_config)(**{**runtime_config.__dict__, "send_timeout_seconds": 0.01})
        gateway = OneBotGateway(runtime_config)
        gateway._self_id = "100"
        gateway._group_resolved = True
        socket = SilentSocket()
        gateway._socket = socket

        result = await gateway.send_text("reply")

        assert result.sent is False
        assert result.state == "unknown"
        assert result.reason == "send_unknown"
        assert len([item for item in socket.requests if item["action"] == "send_group_msg"]) == 1

    asyncio.run(scenario())


class ActionSocket:
    def __init__(self, gateway):
        self.gateway = gateway
        self.requests = []

    async def send_json(self, payload):
        self.requests.append(payload)
        asyncio.get_running_loop().call_soon(
            asyncio.create_task,
            self.gateway._handle_payload(
                {
                    "status": "ok",
                    "retcode": 0,
                    "data": {"message_id": "900"},
                    "echo": payload["echo"],
                }
            ),
        )


class SilentSocket:
    def __init__(self):
        self.requests = []

    async def send_json(self, payload):
        self.requests.append(payload)
