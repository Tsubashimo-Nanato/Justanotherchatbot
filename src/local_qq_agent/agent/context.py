from __future__ import annotations

from dataclasses import dataclass

from local_qq_agent.agent.persona import PersonaGuard
from local_qq_agent.agent.social_state import SocialStateTracker
from local_qq_agent.memory.store import EventRecord, SQLiteMemoryStore


RECENT_CONTEXT_LIMIT = 6
STYLE_SAMPLE_LIMIT = 5


@dataclass(frozen=True)
class BuiltContext:
    messages: list[dict[str, str]]
    memory_lines: list[str]
    recent_lines: list[str]


class ContextBuilder:
    def __init__(
        self,
        store: SQLiteMemoryStore,
        persona_guard: PersonaGuard,
        social_state: SocialStateTracker | None = None,
    ) -> None:
        self.store = store
        self.persona_guard = persona_guard
        self.social_state = social_state or SocialStateTracker(store)

    def build(
        self,
        user_name: str,
        user_message: str,
        external_context: str = "",
        *,
        fast_reply: bool = False,
        thinking_directive: str = "",
    ) -> BuiltContext:
        memory_records = self.store.search_memories(user_message, limit=6)
        recent_memories = self.store.recent_memories(limit=6)
        recent_events = self.store.recent_events(limit=60)
        social_snapshot = self.social_state.snapshot(user_name)

        memory_lines = self._memory_lines([*memory_records, *recent_memories])
        memory_lines.extend(f"social_state: {line}" for line in social_snapshot.prompt_lines())
        memory_lines.extend(self._style_sample_lines(recent_events))
        recent_lines = self._recent_conversation_lines(recent_events)

        fast_rule = ""
        if fast_reply:
            fast_rule = "\nFast path: this is a simple chat turn. Reply directly, short, and do not overthink."

        system_prompt = (
            f"{self.persona_guard.build_system_prompt(memory_lines)}\n\n"
            "语用判断: 先判断最新消息是认真提问、讽刺、反问、抱怨、玩笑、命令还是延续上一轮。"
            " 如果已经能看出真实矛盾，不要只回答字面问题。"
            "Generation rules: output only the QQ message text. Do not output reasoning. "
            "First read the latest turn pragmatically: literal question, joke, sarcasm, complaint, command, or follow-up. "
            "Do not force a reply if the turn is only ambient side-chat. "
            "If it is directed at you or quoting/following you, reply in character. "
            "Match language to the latest message and recent context; do not default to Chinese for English turns. "
            f"{fast_rule}\n"
            f"{thinking_directive}"
        )
        user_prompt = self._build_user_prompt(user_name, user_message, recent_lines, external_context)

        return BuiltContext(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            memory_lines=memory_lines,
            recent_lines=recent_lines,
        )

    def _memory_lines(self, memories) -> list[str]:
        seen: set[int] = set()
        lines: list[str] = []
        for memory in memories:
            if memory.id in seen:
                continue
            seen.add(memory.id)
            lines.append(f"{memory.kind}: {memory.summary}")
        return lines

    def _recent_conversation_lines(self, events: list[EventRecord]) -> list[str]:
        lines: list[str] = []
        for event in events:
            if not self._event_belongs_to_conversation(event):
                continue
            sender = event.metadata.get("sender_name") or event.source
            text = event.metadata.get("clean_text") or event.content
            lines.append(f"{sender}: {str(text).strip()}")
        return lines[-RECENT_CONTEXT_LIMIT:]

    def _style_sample_lines(self, events: list[EventRecord]) -> list[str]:
        config = self.persona_guard.config
        target = config.style_learning_target_user.strip()
        if not config.style_learning_enabled or not target:
            return []

        samples: list[str] = []
        for event in events:
            if event.kind != "group_message":
                continue
            sender = str(event.metadata.get("sender_name") or event.source).strip()
            if not self._same_person_hint(sender, target):
                continue
            text = str(event.metadata.get("clean_text") or event.content).strip()
            if not text:
                continue
            samples.append(text)

        return [f"style_sample_from_{target}: {sample}" for sample in samples[-STYLE_SAMPLE_LIMIT:]]

    def _same_person_hint(self, sender: str, target: str) -> bool:
        left = sender.casefold().replace(" ", "")
        right = target.casefold().replace(" ", "")
        if not left or not right:
            return False
        return left == right or left in right or right in left

    def _event_belongs_to_conversation(self, event: EventRecord) -> bool:
        if event.kind in {"assistant_reply", "assistant_blocked", "assistant_placeholder"}:
            return True
        if event.kind != "group_message":
            return False

        metadata = event.metadata or {}
        if metadata.get("origin") != "qq_loop":
            return True
        return metadata.get("agent_action") in {"reply", "no_reply", "context_only"}

    def _build_user_prompt(
        self,
        user_name: str,
        user_message: str,
        recent_lines: list[str],
        external_context: str,
    ) -> str:
        recent_text = "\n".join(recent_lines[-RECENT_CONTEXT_LIMIT:]) if recent_lines else "none"
        external_text = external_context.strip() or "none"
        return (
            "Current group context:\n"
            f"recent messages:\n{recent_text}\n\n"
            f"external/tool evidence:\n{external_text}\n\n"
            f"latest sender: {user_name}\n"
            f"latest message: {user_message}\n\n"
            "Decide the real intent from context, especially the 真实语气和意图, then output only the text you would send to QQ."
            " 如果这句话是讽刺、反问、抱怨或玩笑，不要只回答字面问题，也不要只回一个疑问词。"
        )
