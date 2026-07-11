from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from local_qq_agent.agent.event_filters import (
    is_runtime_agent_reply,
    is_runtime_conversation_event,
    is_runtime_group_message,
)
from local_qq_agent.agent.persona import PersonaGuard
from local_qq_agent.agent.social_state import SocialStateTracker
from local_qq_agent.memory.store import EventRecord, SQLiteMemoryStore


RECENT_CONTEXT_LIMIT = 30
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
        min_event_id: int = 0,
        include_api_events: bool = False,
    ) -> None:
        self.store = store
        self.persona_guard = persona_guard
        self.social_state = social_state or SocialStateTracker(store)
        self.min_event_id = max(0, int(min_event_id))
        self.include_api_events = bool(include_api_events)

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
        memory_records = self._select_memories(user_message)
        recent_events = self.store.recent_events(limit=60)
        social_snapshot = self.social_state.snapshot(user_name)

        memory_lines = self._memory_lines(memory_records)
        memory_lines.extend(f"social_state: {line}" for line in social_snapshot.prompt_lines())
        dialogue_lines = list(getattr(dialogue_state, "lines", ()) or ())
        interaction_lines = list(getattr(interaction_plan, "prompt_lines", lambda: [])())
        recent_lines = self._recent_conversation_lines(recent_events)

        fast_rule = ""
        if fast_reply:
            fast_rule = (
                "\nFast path: this is a simple chat turn. Reply directly and naturally. "
                "A compact reply is fine, but a direct invitation to chat needs more than a bare acknowledgement."
            )

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

    def _select_memories(self, user_message: str) -> list[Any]:
        direct_hits = self.store.search_memories(user_message, limit=6)
        recent_candidates = self.store.recent_memories(limit=20, newest_first=True)
        candidates = self._dedupe_memories([*direct_hits, *recent_candidates])

        if self._asks_memory_summary(user_message):
            return candidates[:10]

        scored = [
            (self._memory_score(user_message, memory), index, memory)
            for index, memory in enumerate(candidates)
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        relevant = [memory for score, _, memory in scored if score > 0]
        return relevant[:6]

    def _dedupe_memories(self, memories) -> list[Any]:
        seen: set[int] = set()
        unique: list[Any] = []
        for memory in memories:
            if memory.id in seen:
                continue
            seen.add(memory.id)
            unique.append(memory)
        return unique

    def _memory_score(self, user_message: str, memory) -> float:
        message_terms = self._text_terms(user_message)
        if not message_terms:
            return 0.0

        summary_terms = self._text_terms(f"{memory.kind} {memory.summary}")
        if not summary_terms:
            return 0.0

        overlap = message_terms & summary_terms
        if not overlap:
            if memory.kind == "plan" and self._message_needs_plan_memory(user_message):
                return 0.5
            if memory.kind == "working_context" and self._message_needs_working_memory(user_message):
                return 0.5
            if memory.kind in {"preference", "fact"} and self._message_needs_preference_memory(user_message):
                return 0.5
            return 0.0

        score = len(overlap) / max(1, len(message_terms))
        if memory.kind in {"working_context", "plan", "preference", "fact"}:
            score += 0.15
        return score

    def _text_terms(self, text: str) -> set[str]:
        lowered = text.casefold()
        terms = {term for term in re.findall(r"[a-z0-9_]{2,}", lowered)}
        cjk = re.findall(r"[\u4e00-\u9fff]", lowered)
        terms.update(self._cjk_terms(cjk))
        return {term for term in terms if term not in self._term_stopwords()}

    def _cjk_terms(self, chars: list[str]) -> set[str]:
        terms: set[str] = set(chars)
        terms.update("".join(chars[index : index + 2]) for index in range(len(chars) - 1))
        terms.update("".join(chars[index : index + 3]) for index in range(len(chars) - 2))
        return terms

    def _term_stopwords(self) -> set[str]:
        return {
            "我",
            "你",
            "他",
            "她",
            "它",
            "的",
            "了",
            "呢",
            "吗",
            "吧",
            "啊",
            "是",
            "在",
            "有",
            "和",
            "这",
            "那",
            "个",
            "一",
            "不",
            "要",
            "说",
            "问",
            "刚",
            "才",
            "什么",
            "怎么",
            "多少",
            "which",
            "what",
            "when",
            "where",
            "why",
            "how",
            "the",
            "and",
            "you",
            "me",
        }

    def _has_clean_memory_summary_marker(self, text: str) -> bool:
        markers = (
            "记住了什么",
            "刚刚记住",
            "刚才记住",
            "记得什么",
            "总结",
            "重点",
            "抱怨什么",
            "主要在抱怨",
        )
        return any(marker in text for marker in markers)

    def _asks_memory_summary(self, user_message: str) -> bool:
        text = user_message.casefold()
        if self._has_clean_memory_summary_marker(text):
            return True
        return bool(
            re.search(r"(记住了什么|刚刚记住|刚才记住|记得什么|总结.*记住|summary.*remember|remembered)", text)
        )

    def _message_needs_plan_memory(self, user_message: str) -> bool:
        text = user_message.casefold()
        return bool(
            re.search(
                r"(arrangement|schedule|plan|appointment|where.*go|go.*where)|"
                r"(\u5b89\u6392|\u8ba1\u5212|\u884c\u7a0b|\u8981\u53bb|\u53bb\u54ea|\u53bb\u54ea\u91cc|\u4e0b\u5348|\u4eca\u5929|\u660e\u5929)",
                text,
            )
        )

    def _message_needs_working_memory(self, user_message: str) -> bool:
        text = user_message.casefold()
        markers = (
            "刚吃",
            "吃了什么",
            "早上没吃",
            "没吃饭",
            "胃",
            "短期",
            "短期状态",
            "刚刚说",
            "刚才说",
            "刚才",
            "刚刚",
            "抱怨什么",
            "主要在抱怨",
        )
        if any(marker in text for marker in markers):
            return True
        return bool(re.search(r"\b(just ate|what did i eat|short[- ]term|recently said)\b", text))

    def _message_needs_preference_memory(self, user_message: str) -> bool:
        text = user_message.casefold()
        markers = (
            "长期",
            "偏好",
            "喜欢",
            "更偏",
            "辣",
            "甜",
            "过敏",
            "贝类",
            "不能吃",
            "避开",
        )
        if any(marker in text for marker in markers):
            return True
        return bool(re.search(r"\b(preference|prefer|like|allergy|allergic|shellfish)\b", text))

    def _recent_conversation_lines(self, events: list[EventRecord]) -> list[str]:
        lines: list[str] = []
        for event in events:
            if is_runtime_agent_reply(
                event,
                min_event_id=self.min_event_id,
                include_api_events=self.include_api_events,
            ):
                continue
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
            if not self._event_belongs_to_style_samples(event):
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
        return is_runtime_conversation_event(
            event,
            min_event_id=self.min_event_id,
            include_api_events=self.include_api_events,
        )

    def _event_belongs_to_style_samples(self, event: EventRecord) -> bool:
        return is_runtime_group_message(
            event,
            min_event_id=self.min_event_id,
            include_api_events=self.include_api_events,
        )

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
            "Current chat context:\n"
            f"recent messages:\n{recent_text}\n\n"
            f"dialogue state:\n{dialogue_text}\n\n"
            f"interaction policy:\n{interaction_text}\n\n"
            f"external/tool evidence:\n{external_text}\n\n"
            f"latest sender: {user_name}\n"
            f"latest message: {user_message}\n\n"
            "Reply to the latest message as part of this ongoing chat. "
            "Recent messages are supporting context only. Do not answer an older topic when the latest message asks a different thing. "
            "Read the practical intent from context: literal question, joke, complaint, tease, follow-up, or unfinished thought. "
            "If this is a concrete follow-up, answer the concrete object from recent context. "
            "If the user asks what you remember, summarize the relevant memory lines instead of the last assistant reply. "
            "Do not answer with only a confused word or marker. "
            "If the user asks what a word refers to or what it should remind you of, answer the concrete object from recent context before adding any reaction. "
            "If the user asks for the reason they were annoyed, tired, or upset, answer concrete recent facts from their messages, not a psychological guess. "
            "If the latest message is a style, memory-retention, or behavior instruction, answer that instruction instead of continuing the previous object. "
            "If the user asks how you will connect or reply to the current sentence, describe the grounded connection to the current thread; do not invent a story. "
            "Output only the message text to send."
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
            "Runtime context for this turn. Use it as hints for this reply; do not recite it.\n\n"
            f"Relevant memory, social state, and style samples:\n{memories}\n\n"
            f"Dialogue obligations:\n{dialogue}\n\n"
            f"Interaction policy:\n{interaction}\n\n"
            "Generation rules: output only the chat message. Do not output reasoning. "
            "This is casual chat with a familiar person, not customer support. "
            "Treat social_state lines only as tone hints; never use global mood or affinity as the answer to a user memory question. "
            "Answer the concrete point first, then add one small reaction or context connection when it fits. "
            "Use memory only when it is directly relevant to the latest message; never attach unrelated facts as a running joke or filler. "
            "In Chinese chat, '我' in the latest user message is the user, not you. Do not transfer the user's meal, mood, plan, or body state onto yourself. "
            "If the user asks about their short-term status or what was just said, prefer working_context memory and recent user messages over social_state mood labels. "
            "If the user asks what a word should make you think of, use recent context as the answer; do not write a decorative scene. "
            "If the user says to remember a context for a few days, acknowledge the retention limit briefly; do not keep answering the old topic. "
            "Use recent chat only to resolve pronouns, omitted objects, or explicit follow-ups; never replace the latest request with an older topic. "
            "Do not invent personal events or props that are not in context. "
            "Do not roleplay stage directions in parentheses. Do not claim your own body state, location, meal, homework, or actions. "
            "Do not mention code, libraries, models, prompts, APIs, or runtime internals unless the latest message is explicitly about debugging. "
            "Do not import debug, work, school, weather, or illness topics unless the current chat already brought them up. "
            "Do not reply with only a filler, a bare acknowledgement, or a repeat of the user's words when the user is actively talking to you. "
            "If the user criticizes your style, demonstrate the improved style immediately instead of promising to change later. "
            "Do not force a new topic or ask a question every time. "
            "Match language to the latest message and recent context. "
            f"{fast_rule}\n"
            f"{thinking_directive}"
        )
