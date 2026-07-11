import asyncio
from dataclasses import dataclass

from local_qq_agent.agent.core import AgentResult
from local_qq_agent.config import OneBotConfig
from local_qq_agent.memory import SQLiteMemoryStore
from local_qq_agent.onebot import OneBotMessage, OneBotSendResult
from local_qq_agent.server.agent_loop import AgentLoop


def test_redelivered_platform_message_calls_model_and_send_once(tmp_path):
    async def scenario():
        gateway = FakeGateway()
        agent = FakeAgent()
        loop = build_loop(tmp_path, gateway, agent)
        await loop.start()
        message = incoming("300", "hello .enforce")

        await gateway.emit(message)
        await gateway.emit(message)
        await wait_until(lambda: bool(loop.status()["recent_decisions"]))
        await loop.stop()

        assert agent.calls == ["hello .enforce"]
        assert len(gateway.sends) == 1
        assert gateway.sends[0][1].message_id == "300"
        rows = loop.store.recent_transport_turns()
        assert len([row for row in rows if row["message_id"] == "300"]) == 1

    asyncio.run(scenario())


def test_fast_same_sender_messages_are_one_turn_with_all_source_ids(tmp_path):
    async def scenario():
        gateway = FakeGateway()
        agent = FakeAgent()
        loop = build_loop(tmp_path, gateway, agent, quiet=0.03)
        await loop.start()

        await gateway.emit(incoming("301", "first"))
        await gateway.emit(incoming("302", "second"))
        await wait_until(lambda: bool(loop.status()["recent_decisions"]))
        await loop.stop()

        assert agent.calls == ["first\nsecond"]
        assert len(gateway.sends) == 1
        decision = loop.status()["recent_decisions"][-1]
        assert decision["metadata"]["send_result"]["reply_to_message_id"] == "302"

    asyncio.run(scenario())


def build_loop(tmp_path, gateway, agent, *, quiet=0.01):
    return AgentLoop(
        agent=agent,
        gateway=gateway,
        store=SQLiteMemoryStore(tmp_path / "memory.sqlite3"),
        config=OneBotConfig(
            reverse_ws_path="/onebot/v11/ws",
            access_token="",
            target_group_id="200",
            target_group_name="target",
            target_sender_name="owner",
            bot_sender_name="bot",
            max_messages_per_tick=10,
            ignore_existing_on_start=True,
            turn_quiet_period_seconds=quiet,
        ),
    )


def incoming(message_id, text):
    return OneBotMessage(
        message_id=message_id,
        self_id="100",
        group_id="200",
        user_id="400",
        sender_name="owner",
        text=text,
        timestamp=1,
    )


async def wait_until(predicate, timeout=2.0):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


@dataclass
class FakeStatus:
    ready: bool = True
    target_group_id: str = "200"
    target_group_name: str = "target"

    def to_dict(self):
        return self.__dict__.copy()


class FakeGateway:
    def __init__(self):
        self.listeners = []
        self.sends = []

    def add_message_listener(self, listener):
        self.listeners.append(listener)

    def status(self):
        return FakeStatus()

    async def history(self, count=30):
        return []

    async def emit(self, message):
        for listener in self.listeners:
            await listener(message)

    async def send_text(self, text, *, reply_to=None):
        self.sends.append((text, reply_to))
        return OneBotSendResult(
            sent=True,
            reason="sent",
            text=text,
            message_id=f"out-{len(self.sends)}",
            reply_to_message_id=reply_to.message_id if reply_to else "",
            state="sent",
        )


class FakeSocialState:
    def ensure_contact(self, *, user_name, **kwargs):
        return type("Contact", (), {"user_name": user_name})()


class FakePersonaConfig:
    style_learning_target_user = "owner"


class FakePersonaGuard:
    config = FakePersonaConfig()
    reply_aliases = ()


class FakeAgent:
    def __init__(self):
        self.calls = []
        self.social_state = FakeSocialState()
        self.persona_guard = FakePersonaGuard()
        self.model_client = None

    async def respond_to_incoming(self, *, message, **kwargs):
        self.calls.append(message)
        return AgentResult(
            action="reply",
            reply="response",
            reason="test",
            used_model=True,
            blocked=False,
            metadata={},
        )
