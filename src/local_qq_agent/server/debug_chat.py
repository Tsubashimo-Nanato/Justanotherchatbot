from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import time
from typing import Any

from local_qq_agent.agent import PersonaGuard
from local_qq_agent.memory import MemoryRecord, SQLiteMemoryStore
from local_qq_agent.model.openai_client import ModelReply
from local_qq_agent.paths import ensure_parent


THINK_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class DebugChatTurn:
    role: str
    content: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class DebugChatSession:
    def __init__(self, *, store: SQLiteMemoryStore, log_dir: Path) -> None:
        self.store = store
        self.log_dir = log_dir
        self.enabled = False
        self.session_id = ""
        self.log_path: Path | None = None
        self.transcript: list[DebugChatTurn] = []
        self.latest_result: dict[str, Any] | None = None

    def start(self) -> dict[str, Any]:
        if not self.enabled:
            self.session_id = datetime.now(UTC).strftime("debug_chat_%Y%m%d_%H%M%S")
            self.log_path = self.log_dir / f"{self.session_id}.jsonl"
            ensure_parent(self.log_path)
            self.transcript = []
            self.latest_result = None
        self.enabled = True
        return self.status()

    def stop(self) -> dict[str, Any]:
        self.enabled = False
        self.transcript = []
        self.latest_result = None
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "session_id": self.session_id,
            "message_count": len(self.transcript),
            "log_path": str(self.log_path or ""),
            "latest_result": self.latest_result,
            "transcript": [turn.to_dict() for turn in self.transcript[-40:]],
        }

    async def send(
        self,
        *,
        message: str,
        user_name: str,
        persona_guard: PersonaGuard,
        model_client: Any,
        max_tokens: int = 700,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("debug chat is disabled")
        clean_message = " ".join(message.split()).strip()
        if not clean_message:
            raise ValueError("message must not be empty")

        started_at = time.perf_counter()
        memory_lines = self._memory_lines(clean_message)
        messages = self._build_messages(
            user_name=user_name.strip() or "debugger",
            message=clean_message,
            persona_guard=persona_guard,
            memory_lines=memory_lines,
        )
        reply = await self._call_model(model_client, messages=messages, max_tokens=max_tokens)
        parsed = self._parse_reply(reply.content)
        elapsed = time.perf_counter() - started_at

        user_turn = DebugChatTurn(role="user", content=clean_message, created_at=self._now())
        assistant_turn = DebugChatTurn(role="assistant", content=parsed["reply"], created_at=self._now())
        self.transcript.extend([user_turn, assistant_turn])

        result = {
            "enabled": self.enabled,
            "session_id": self.session_id,
            "reply": parsed["reply"],
            "would_reply": parsed["would_reply"],
            "debug_reason": parsed["debug_reason"],
            "parse_status": parsed["parse_status"],
            "raw_model_content": reply.content,
            "model": reply.model,
            "elapsed_seconds": round(elapsed, 3),
            "latency_seconds": round(reply.latency_seconds, 3),
            "usage": reply.usage,
            "tokens_per_second": reply.tokens_per_second,
            "rewrite": {
                "used": False,
                "reason": "debug_chat_does_not_run_main_quality_rewrite",
            },
            "memory": {
                "read_only": True,
                "lines": memory_lines,
                "count": len(memory_lines),
            },
            "transcript": [turn.to_dict() for turn in self.transcript[-40:]],
            "log_path": str(self.log_path or ""),
        }
        self.latest_result = result
        self._append_log(
            {
                "created_at": self._now(),
                "user": user_turn.to_dict(),
                "assistant": assistant_turn.to_dict(),
                "result": self._log_safe_result(result),
            }
        )
        return result

    def _build_messages(
        self,
        *,
        user_name: str,
        message: str,
        persona_guard: PersonaGuard,
        memory_lines: list[str],
    ) -> list[dict[str, str]]:
        system_prompt = persona_guard.build_system_prompt(memory_lines)
        debug_contract = (
            "This is an isolated one-on-one debug chat. It is not the QQ/WeChat loop. "
            "Read persona and memory, but do not create or modify memory. "
            "Always answer the user in character. Also decide whether this message would deserve a reply "
            "inside a group chat, then report that decision only in JSON fields. "
            "Return strict JSON only: "
            '{"reply":"visible reply text","would_reply":true,"debug_reason":"brief reason"}. '
            "Do not include markdown fences or extra text."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": debug_contract},
        ]
        for turn in self.transcript[-12:]:
            role = "assistant" if turn.role == "assistant" else "user"
            messages.append({"role": role, "content": turn.content})
        messages.append({"role": "user", "content": f"{user_name}: {message}"})
        return messages

    async def _call_model(self, model_client: Any, *, messages: list[dict[str, str]], max_tokens: int) -> ModelReply:
        try:
            return await model_client.chat(messages, max_tokens=max_tokens, operation="simple_chat")
        except TypeError:
            return await model_client.chat(messages, max_tokens=max_tokens)

    def _parse_reply(self, content: str) -> dict[str, Any]:
        cleaned = THINK_BLOCK_PATTERN.sub("", content).strip()
        decoded = self._decode_json_object(cleaned)
        if decoded is None:
            return {
                "reply": cleaned or content.strip(),
                "would_reply": True,
                "debug_reason": "model_output_was_not_json",
                "parse_status": "parse_failed",
            }
        reply = str(decoded.get("reply", "")).strip()
        if not reply:
            reply = cleaned or "(debug chat produced an empty reply)"
        return {
            "reply": reply,
            "would_reply": bool(decoded.get("would_reply", True)),
            "debug_reason": str(decoded.get("debug_reason", "")).strip() or "no debug reason returned",
            "parse_status": "ok",
        }

    def _decode_json_object(self, text: str) -> dict[str, Any] | None:
        text = text.strip()
        if not text:
            return None
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            decoded = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None

    def _memory_lines(self, query: str) -> list[str]:
        memories: list[MemoryRecord] = []
        seen: set[int] = set()
        for memory in self.store.search_memories(query, limit=6):
            memories.append(memory)
            seen.add(memory.id)
        for memory in self.store.recent_memories(limit=6, newest_first=True):
            if memory.id in seen:
                continue
            memories.append(memory)
            seen.add(memory.id)
        return [f"{memory.kind}: {memory.summary}" for memory in memories[:10]]

    def _append_log(self, payload: dict[str, Any]) -> None:
        if self.log_path is None:
            return
        ensure_parent(self.log_path)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def _log_safe_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "reply": result.get("reply", ""),
            "would_reply": result.get("would_reply"),
            "debug_reason": result.get("debug_reason", ""),
            "parse_status": result.get("parse_status", ""),
            "model": result.get("model", ""),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "latency_seconds": result.get("latency_seconds"),
            "usage": result.get("usage", {}),
            "tokens_per_second": result.get("tokens_per_second", {}),
            "rewrite": result.get("rewrite", {}),
            "memory_count": result.get("memory", {}).get("count", 0),
        }

    def _now(self) -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")
