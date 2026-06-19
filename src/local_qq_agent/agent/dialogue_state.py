from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from local_qq_agent.memory.store import EventRecord, SQLiteMemoryStore


@dataclass(frozen=True)
class DialogueState:
    obligation: str
    reason: str
    lines: tuple[str, ...]
    recent_agent_replies: tuple[str, ...]
    recent_user_turns: tuple[str, ...]
    metadata: dict[str, Any]

    @property
    def requires_reply(self) -> bool:
        return self.obligation in {"answer_required", "repair_required"}

    def to_metadata(self) -> dict[str, Any]:
        return asdict(self)


class DialogueStateTracker:
    def __init__(self, store: SQLiteMemoryStore, *, recent_event_limit: int = 80) -> None:
        self.store = store
        self.recent_event_limit = max(8, recent_event_limit)

    def for_turn(self, *, user_name: str, message: str, reply_to_bot: bool) -> DialogueState:
        events = self.store.recent_events(limit=self.recent_event_limit)
        agent_replies = self._recent_agent_replies(events)
        user_turns = self._recent_user_turns(events, user_name=user_name)
        question_like = self._is_question_or_clarification(message)
        repair_like = reply_to_bot and question_like and bool(agent_replies)

        if repair_like:
            obligation = "repair_required"
            reason = "quoted_or_followup_question_about_previous_agent_reply"
        elif reply_to_bot:
            obligation = "answer_required"
            reason = "message_replies_to_agent"
        else:
            obligation = "none"
            reason = "no_active_dialogue_obligation"

        lines = self._prompt_lines(
            obligation=obligation,
            reason=reason,
            message=message,
            agent_replies=agent_replies,
            user_turns=user_turns,
            question_like=question_like,
        )
        return DialogueState(
            obligation=obligation,
            reason=reason,
            lines=tuple(lines),
            recent_agent_replies=tuple(agent_replies),
            recent_user_turns=tuple(user_turns),
            metadata={
                "reply_to_bot": reply_to_bot,
                "question_or_clarification": question_like,
                "recent_agent_reply_count": len(agent_replies),
                "recent_user_turn_count": len(user_turns),
            },
        )

    def _recent_agent_replies(self, events: list[EventRecord]) -> list[str]:
        replies: list[str] = []
        for event in events:
            if event.kind not in {"assistant_reply", "assistant_blocked"}:
                continue
            text = event.content.strip()
            if not text or text.startswith("Command resolved:"):
                continue
            replies.append(text)
        return replies[-4:]

    def _recent_user_turns(self, events: list[EventRecord], *, user_name: str) -> list[str]:
        turns: list[str] = []
        for event in events:
            if event.kind != "group_message":
                continue
            sender = str(event.metadata.get("sender_name") or event.source).strip()
            if sender != user_name:
                continue
            text = str(event.metadata.get("clean_text") or event.content).strip()
            if text:
                turns.append(text)
        return turns[-4:]

    def _is_question_or_clarification(self, message: str) -> bool:
        text = message.strip().casefold()
        if not text:
            return False
        if "?" in text or "？" in text:
            return True

        interrogatives = (
            "what",
            "which",
            "who",
            "where",
            "when",
            "why",
            "how",
            "kind of",
            "answer me",
            "tell me",
            "什么",
            "哪",
            "谁",
            "哪里",
            "几",
            "怎么",
            "为什么",
            "到底",
            "回答",
            "说清楚",
            "解释",
        )
        return any(marker in text for marker in interrogatives)

    def _prompt_lines(
        self,
        *,
        obligation: str,
        reason: str,
        message: str,
        agent_replies: list[str],
        user_turns: list[str],
        question_like: bool,
    ) -> list[str]:
        if obligation == "none" and not agent_replies:
            return []

        lines = [
            f"dialogue_obligation: {obligation}; reason={reason}",
        ]
        if obligation == "repair_required":
            lines.append(
                "dialogue_rule: The latest turn is a clarification or follow-up about what the character just said. "
                "Answer the concrete question directly and repair unclear wording instead of contradicting or dodging."
            )
        elif obligation == "answer_required":
            lines.append(
                "dialogue_rule: The latest turn replies to the character. Treat it as an active conversation, not ambient group chat."
            )
        elif question_like:
            lines.append(
                "dialogue_rule: The latest turn looks question-like. Use recent context to decide whether it asks about the character's previous words."
            )

        if agent_replies:
            lines.append(
                "consistency_rule: Treat recent_agent_replies as things the character just said. "
                "If they are unclear or conflict, repair the wording and preserve continuity instead of inventing a new incompatible self-fact."
            )
            lines.append("recent_agent_replies:")
            lines.extend(f"- {reply}" for reply in agent_replies[-3:])
        if user_turns:
            lines.append("recent_user_turns:")
            lines.extend(f"- {turn}" for turn in user_turns[-3:])

        if self._asks_for_concrete_object(message):
            lines.append(
                "answer_rule: If the user asks what/which/kind, provide the concrete object from context. "
                "Do not reinterpret an ordinary object question as abstract unless prior context clearly requires it."
            )
        return lines

    def _asks_for_concrete_object(self, message: str) -> bool:
        text = message.casefold()
        return bool(
            re.search(r"\b(what|which|kind of)\b", text)
            or re.search(r"(什么|哪种|哪个|哪一个|到底)", text)
        )
