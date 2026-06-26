from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    dialogue_lines: list[str]
    interaction_lines: list[str]


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
        dialogue_state: Any | None = None,
        interaction_plan: Any | None = None,
    ) -> BuiltContext:
        memory_records = self.store.search_memories(user_message, limit=6)
        recent_memories = self.store.recent_memories(limit=6)
        recent_events = self.store.recent_events(limit=60)
        social_snapshot = self.social_state.snapshot(user_name)

        memory_lines = self._memory_lines([*memory_records, *recent_memories])
        memory_lines.extend(f"social_state: {line}" for line in social_snapshot.prompt_lines())
        memory_lines.extend(self._style_sample_lines(recent_events))
        dialogue_lines = list(getattr(dialogue_state, "lines", ()) or ())
        interaction_lines = list(getattr(interaction_plan, "prompt_lines", lambda: [])())
        recent_lines = self._recent_conversation_lines(recent_events)

        fast_rule = ""
        if fast_reply:
            fast_rule = "\nFast path: this is a simple chat turn. Reply directly, short, and do not overthink."

        system_prompt = self.persona_guard.build_system_prompt([])
        runtime_prompt = self._runtime_prompt(
            memory_lines=memory_lines,
            dialogue_lines=dialogue_lines,
            interaction_lines=interaction_lines,
            thinking_directive=thinking_directive,
            fast_rule=fast_rule,
        )
        user_prompt = self._build_user_prompt(
            user_name,
            user_message,
            recent_lines,
            external_context,
            dialogue_lines,
            interaction_lines,
        )

        return BuiltContext(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": runtime_prompt},
                {"role": "user", "content": user_prompt},
            ],
            memory_lines=memory_lines,
            recent_lines=recent_lines,
            dialogue_lines=dialogue_lines,
            interaction_lines=interaction_lines,
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
            clean = str(text).strip()
            if clean:
                lines.append(f"{sender}: {clean}")
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
            if text:
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
        dialogue_lines: list[str],
        interaction_lines: list[str],
    ) -> str:
        recent_text = "\n".join(recent_lines[-RECENT_CONTEXT_LIMIT:]) if recent_lines else "none"
        external_text = external_context.strip() or "none"
        dialogue_text = "\n".join(dialogue_lines) if dialogue_lines else "none"
        interaction_text = "\n".join(interaction_lines) if interaction_lines else "none"
        return (
            "Current group context:\n"
            f"recent messages:\n{recent_text}\n\n"
            f"dialogue state:\n{dialogue_text}\n\n"
            f"interaction policy:\n{interaction_text}\n\n"
            f"external/tool evidence:\n{external_text}\n\n"
            f"latest sender: {user_name}\n"
            f"latest message: {user_message}\n\n"
            "Decide the real intent from context, especially the tone and pragmatic intent. "
            "语用判断：看真实语气和意图。If this is sarcasm, a rhetorical jab, complaint, or joke, "
            "不要只回答字面问题; do not answer only the literal words. "
            "If this is a concrete follow-up, answer the concrete object from recent context. "
            "Output only the text to send to QQ."
        )

    def _runtime_prompt(
        self,
        *,
        memory_lines: list[str],
        dialogue_lines: list[str],
        interaction_lines: list[str],
        thinking_directive: str,
        fast_rule: str,
    ) -> str:
        memories = "\n".join(f"- {line}" for line in memory_lines) if memory_lines else "- no relevant memory"
        dialogue = "\n".join(f"- {line}" for line in dialogue_lines) if dialogue_lines else "- none"
        interaction = "\n".join(f"- {line}" for line in interaction_lines) if interaction_lines else "- none"
        return (
            "Runtime context for this turn. This block may change every message; do not treat it as persona text.\n\n"
            f"Relevant memory, social state, and style samples:\n{memories}\n\n"
            f"Dialogue obligations:\n{dialogue}\n\n"
            f"Interaction policy:\n{interaction}\n\n"
            "Generation rules: output only the QQ message text. Do not output reasoning. "
            "First read the latest turn pragmatically: literal question, joke, sarcasm, complaint, command, or follow-up. "
            "语用判断：先看真实语气和意图，尤其是讽刺、抱怨、玩笑和追问；不要只回答字面问题，不要只回一个疑问词。 "
            "Do not force a reply if the turn is only ambient side-chat. "
            "If it is directed at you or quoting/following you, reply in character. "
            "Match language to the latest message and recent context; do not default to Chinese for English turns. "
            f"{fast_rule}\n"
            f"{thinking_directive}"
        )
