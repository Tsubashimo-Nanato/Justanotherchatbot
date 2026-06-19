from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StyleLearningSummary:
    target_user: str
    target_user_message_count: int
    assistant_reply_count: int
    no_reply_count: int
    placeholder_count: int
    feedback_count: int
    low_score_feedback_count: int
    web_tool_count: int
    status: str = "pending_review"
    next_step: str = (
        "Review this clean run log and behavior feedback before producing a style-memory "
        "proposal. Do not rewrite persona anchors automatically."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_style_learning(events: list[dict[str, Any]], *, target_user: str) -> StyleLearningSummary:
    target = target_user.strip()
    target_messages = 0
    assistant_replies = 0
    no_replies = 0
    placeholders = 0
    feedback = 0
    low_feedback = 0
    web_tools = 0

    for event in events:
        kind = str(event.get("kind", ""))
        if kind == "group_message":
            sender = str(event.get("sender", "")).strip()
            if target and sender == target:
                target_messages += 1
            if event.get("web_used"):
                web_tools += 1
        elif kind == "assistant_reply":
            assistant_replies += 1
            if event.get("web_used"):
                web_tools += 1
        elif kind == "assistant_blocked":
            no_replies += 1
        elif kind == "assistant_placeholder":
            placeholders += 1
        elif kind == "behavior_feedback":
            feedback += 1
            score = _as_float(event.get("score"))
            if score is not None and score < 0.35:
                low_feedback += 1

    return StyleLearningSummary(
        target_user=target,
        target_user_message_count=target_messages,
        assistant_reply_count=assistant_replies,
        no_reply_count=no_replies,
        placeholder_count=placeholders,
        feedback_count=feedback,
        low_score_feedback_count=low_feedback,
        web_tool_count=web_tools,
    )


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
