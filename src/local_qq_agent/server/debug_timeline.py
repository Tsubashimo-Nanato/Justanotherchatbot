from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from local_qq_agent.memory import EventRecord


VISIBLE_KINDS = {
    "group_message",
    "loop_decision",
    "assistant_reply",
    "assistant_blocked",
    "assistant_placeholder",
    "behavior_feedback",
    "style_anchor_refresh",
    "run_log_exported",
    "loop_started",
    "loop_stopped",
}


@dataclass(frozen=True)
class TimelineItem:
    event_id: int
    time: str
    kind: str
    who: str
    message: str
    decision: str
    reason: str
    reply: str
    sent: bool | None
    tokens: dict[str, Any]
    web: dict[str, Any]
    trace_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "time": self.time,
            "kind": self.kind,
            "who": self.who,
            "message": self.message,
            "decision": self.decision,
            "reason": self.reason,
            "reply": self.reply,
            "sent": self.sent,
            "tokens": self.tokens,
            "web": self.web,
            "trace_id": self.trace_id,
        }


def build_debug_timeline(events: list[EventRecord], *, limit: int = 80) -> list[dict[str, Any]]:
    linked_assistant_ids = _linked_assistant_event_ids(events)
    decision_identities = _loop_decision_identities(events)
    latest_group_event_ids = _latest_group_event_ids(events, decision_identities)
    items = [
        _timeline_item(event)
        for event in events
        if _is_visible_event(
            event,
            linked_assistant_ids=linked_assistant_ids,
            decision_identities=decision_identities,
            latest_group_event_ids=latest_group_event_ids,
        )
    ]
    visible = [item.to_dict() for item in items if item is not None]
    if limit <= 0:
        return visible
    return visible[-limit:]


def _linked_assistant_event_ids(events: list[EventRecord]) -> set[int]:
    linked: set[int] = set()
    for event in events:
        if event.kind != "loop_decision":
            continue
        assistant_id = (event.metadata or {}).get("assistant_event_id")
        if isinstance(assistant_id, int):
            linked.add(assistant_id)
    return linked


def _loop_decision_identities(events: list[EventRecord]) -> set[str]:
    identities: set[str] = set()
    for event in events:
        if event.kind != "loop_decision":
            continue
        identity = _loop_decision_identity(event)
        if identity:
            identities.add(identity)
    return identities


def _latest_group_event_ids(events: list[EventRecord], decision_identities: set[str]) -> set[int]:
    latest_by_identity: dict[str, int] = {}
    for event in events:
        if event.kind != "group_message":
            continue
        identity = _group_message_identity(event)
        if not identity or identity in decision_identities:
            continue
        latest_by_identity[identity] = event.id
    return set(latest_by_identity.values())


def _is_visible_event(
    event: EventRecord,
    *,
    linked_assistant_ids: set[int],
    decision_identities: set[str],
    latest_group_event_ids: set[int],
) -> bool:
    if event.kind not in VISIBLE_KINDS or event.id in linked_assistant_ids:
        return False
    if event.kind != "group_message":
        return True

    identity = _group_message_identity(event)
    if not identity:
        return True
    if identity in decision_identities:
        return False
    return event.id in latest_group_event_ids


def _loop_decision_identity(event: EventRecord) -> str:
    metadata = event.metadata or {}
    return _text(
        metadata.get("message_identity")
        or metadata.get("clean_identity")
        or metadata.get("turn_identity")
        or _fallback_identity(metadata.get("sender_name") or event.source, metadata.get("message_text") or event.content)
    )


def _group_message_identity(event: EventRecord) -> str:
    metadata = event.metadata or {}
    return _text(
        metadata.get("clean_identity")
        or metadata.get("message_identity")
        or metadata.get("turn_identity")
        or _fallback_identity(metadata.get("sender_name") or event.source, metadata.get("clean_text") or event.content)
    )


def _fallback_identity(sender: Any, message: Any) -> str:
    who = _text(sender).casefold()
    text = _message_text(message).casefold()
    if not who or not text:
        return ""
    return f"{who}:{text}"


def _timeline_item(event: EventRecord) -> TimelineItem | None:
    metadata = event.metadata or {}
    kind = event.kind
    if kind == "group_message":
        return TimelineItem(
            event_id=event.id,
            time=event.created_at,
            kind=kind,
            who=_text(metadata.get("sender_name") or event.source),
            message=_message_text(metadata.get("clean_text") or event.content),
            decision=_text(metadata.get("agent_action")),
            reason=_text(metadata.get("agent_reason")),
            reply="",
            sent=None,
            tokens={},
            web={},
            trace_id="",
        )

    if kind == "loop_decision":
        return TimelineItem(
            event_id=event.id,
            time=event.created_at,
            kind=kind,
            who=_text(metadata.get("sender_name") or event.source),
            message=_message_text(metadata.get("message_text") or event.content),
            decision=_text(metadata.get("action")),
            reason=_text(metadata.get("reason")),
            reply=_message_text(_loop_decision_reply(metadata)),
            sent=_bool_or_none(metadata.get("sent")),
            tokens=_token_summary(metadata),
            web=_web_summary(metadata),
            trace_id=_text(metadata.get("provider_trace_id")),
        )

    if kind in {"assistant_reply", "assistant_blocked", "assistant_placeholder"}:
        return TimelineItem(
            event_id=event.id,
            time=event.created_at,
            kind=kind,
            who="agent",
            message="",
            decision="reply" if kind == "assistant_reply" else ("placeholder" if kind == "assistant_placeholder" else "blocked"),
            reason=_text(metadata.get("reason")),
            reply=_message_text(event.content),
            sent=_bool_or_none(metadata.get("sent")),
            tokens=_token_summary(metadata),
            web=_web_summary(metadata),
            trace_id=_text(metadata.get("provider_trace_id")),
        )

    if kind == "behavior_feedback":
        return TimelineItem(
            event_id=event.id,
            time=event.created_at,
            kind=kind,
            who=_text(metadata.get("user_name") or event.source),
            message=_message_text(metadata.get("score_note") or event.content),
            decision="feedback",
            reason=f"score={metadata.get('score_value', '?')}",
            reply=_message_text(metadata.get("recent_reply") or ""),
            sent=None,
            tokens={},
            web={},
            trace_id="",
        )

    if kind in {"style_anchor_refresh", "run_log_exported", "loop_started", "loop_stopped"}:
        return TimelineItem(
            event_id=event.id,
            time=event.created_at,
            kind=kind,
            who=event.source,
            message=_message_text(event.content),
            decision=kind,
            reason=_text(metadata.get("reason") or metadata.get("source")),
            reply="",
            sent=None,
            tokens={},
            web={},
            trace_id="",
        )

    return None


def _loop_decision_reply(metadata: dict[str, Any]) -> str:
    reply = metadata.get("agent_reply") or metadata.get("cleaned_reply")
    if reply:
        return _text(reply)
    nested = metadata.get("metadata")
    if isinstance(nested, dict):
        return _text(nested.get("cleaned_reply") or nested.get("agent_reply"))
    return ""


def _token_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    usage = metadata.get("usage") if isinstance(metadata.get("usage"), dict) else {}
    tps = metadata.get("tokens_per_second") if isinstance(metadata.get("tokens_per_second"), dict) else {}
    prompt = metadata.get("prompt_tokens", usage.get("prompt_tokens"))
    completion = metadata.get("completion_tokens", usage.get("completion_tokens"))
    total = metadata.get("total_tokens", usage.get("total_tokens"))
    return {
        "prompt": prompt,
        "completion": completion,
        "total": total,
        "local": _local_token_summary(metadata.get("token_usage")),
        "api": _api_token_summary(metadata.get("token_usage")),
        "completion_per_second": tps.get("completion_tokens"),
        "latency_seconds": metadata.get("latency_seconds"),
        "thinking_level": metadata.get("thinking_level"),
    }


def _local_token_summary(token_usage: Any) -> dict[str, Any]:
    if not isinstance(token_usage, dict):
        return {}
    total = ((token_usage.get("local") or {}).get("total") or {})
    return {
        "prompt": total.get("prompt"),
        "completion": total.get("completion"),
        "total": total.get("total"),
        "latency_seconds": total.get("latency_seconds"),
    }


def _api_token_summary(token_usage: Any) -> dict[str, Any]:
    if not isinstance(token_usage, dict):
        return {}
    total = ((token_usage.get("api") or {}).get("total") or {})
    return {
        "input": total.get("input"),
        "output": total.get("output"),
        "total": total.get("total"),
        "cached": total.get("cached"),
        "reasoning": total.get("reasoning"),
        "cost_ticks": total.get("cost_ticks"),
        "latency_seconds": total.get("latency_seconds"),
    }


def _web_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    sources = metadata.get("web_sources")
    if not isinstance(sources, list):
        sources = []
    return {
        "used": bool(metadata.get("web_used")),
        "search_used": bool(metadata.get("search_used")),
        "query": _text(metadata.get("web_query")),
        "source_count": len(sources),
    }


def _message_text(value: Any) -> str:
    return _short(_text(value), max_length=360)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _short(value: str, *, max_length: int) -> str:
    text = " ".join(value.split())
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)
