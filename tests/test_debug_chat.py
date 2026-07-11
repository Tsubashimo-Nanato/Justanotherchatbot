import asyncio

from local_qq_agent.memory import SQLiteMemoryStore
from local_qq_agent.model.openai_client import ModelReply
from local_qq_agent.server.debug_chat import DebugChatSession


class FakePersonaGuard:
    def build_system_prompt(self, memory_lines):
        return "persona prompt\n" + "\n".join(memory_lines)


class FakeModelClient:
    def __init__(self):
        self.messages = []
        self.kwargs = {}

    async def chat(self, messages, **kwargs):
        self.messages = messages
        self.kwargs = kwargs
        return ModelReply(
            content='{"reply":"还行，先说你那边。","would_reply":true,"debug_reason":"direct debug chat"}',
            model="fake",
            latency_seconds=0.25,
            usage={"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
            tokens_per_second={"prompt_tokens": 40.0, "completion_tokens": 24.0, "total_tokens": 64.0},
        )


def test_debug_chat_uses_read_only_memory_and_writes_session_log(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.add_memory(kind="preference", summary="tester likes ramen", confidence=0.8)
    session = DebugChatSession(store=store, log_dir=tmp_path / "debug_chat")
    session.start()

    result = asyncio.run(
        session.send(
            message="今天吃什么",
            user_name="tester",
            persona_guard=FakePersonaGuard(),
            model_client=FakeModelClient(),
        )
    )

    assert result["reply"] == "还行，先说你那边。"
    assert result["would_reply"] is True
    assert result["parse_status"] == "ok"
    assert result["memory"]["read_only"] is True
    assert result["memory"]["count"] >= 1
    assert store.recent_events(limit=10) == []
    assert session.log_path is not None
    assert session.log_path.exists()


def test_debug_chat_falls_back_to_raw_text_when_json_parse_fails(tmp_path):
    class RawModel:
        async def chat(self, messages, **kwargs):
            return ModelReply(
                content="嗯，听着不像没事。",
                model="fake",
                latency_seconds=0.1,
                usage={},
            )

    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    session = DebugChatSession(store=store, log_dir=tmp_path / "debug_chat")
    session.start()

    result = asyncio.run(
        session.send(
            message="我胃有点不舒服",
            user_name="tester",
            persona_guard=FakePersonaGuard(),
            model_client=RawModel(),
        )
    )

    assert result["reply"] == "嗯，听着不像没事。"
    assert result["parse_status"] == "parse_failed"
    assert result["debug_reason"] == "model_output_was_not_json"
