import asyncio

from local_qq_agent.config import OneBotConfig
from local_qq_agent.memory import SQLiteMemoryStore
from local_qq_agent.server.agent_loop import AgentLoop
from local_qq_agent.server.instance_guard import AgentInstanceGuard


def test_instance_guard_claim_replaces_previous_owner(tmp_path):
    lease_path = tmp_path / "active_agent_instance.json"
    first = AgentInstanceGuard(lease_path=lease_path, instance_id="first", process_id=100)
    second = AgentInstanceGuard(lease_path=lease_path, instance_id="second", process_id=200)

    first.claim()
    assert first.is_current()

    second.claim()

    assert second.is_current()
    assert not first.is_current()
    assert second.status()["current"]["process_id"] == 200


def test_loop_refuses_to_start_when_instance_is_inactive(tmp_path):
    loop = build_loop(tmp_path, active=False)

    status = asyncio.run(loop.start())

    assert not status["running"]
    assert status["activity"]["stage"] == "inactive_instance"
    assert status["active_instance"] is False


def test_tick_stops_existing_loop_when_instance_is_lost(tmp_path):
    active = {"value": True}
    loop = build_loop(tmp_path, active=lambda: active["value"])

    active["value"] = False
    result = asyncio.run(loop.tick())

    assert result["reason"] == "inactive_agent_instance"
    assert loop.status()["stop_requested"] is True
    assert loop.status()["activity"]["stage"] == "inactive_instance"


def build_loop(tmp_path, *, active=True):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    if callable(active):
        active_callback = active
    else:
        active_callback = lambda: bool(active)
    return AgentLoop(
        agent=None,
        gateway=FakeGateway(),
        store=store,
        config=OneBotConfig(
            reverse_ws_path="/onebot/v11/ws",
            access_token="",
            target_group_id="123",
            target_group_name="target group",
            target_sender_name="target user",
            bot_sender_name="bot user",
            max_messages_per_tick=1,
            ignore_existing_on_start=False,
        ),
        is_active_instance=active_callback,
    )


class FakeStatus:
    target_group_id = "123"
    target_group_name = "target group"
    ready = True

    def to_dict(self):
        return {"ready": True, "target_group_id": "123", "target_group_name": "target group"}


class FakeGateway:
    def add_message_listener(self, listener):
        self.listener = listener

    def status(self):
        return FakeStatus()
