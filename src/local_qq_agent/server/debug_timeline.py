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
        summary_lines = _summary_lines(self)
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
            "status": _status(self),
            "summary": " | ".join(summary_lines),
            "summary_lines": summary_lines,
        }


def build_debug_timeline(events: list[EventRecord], *, limit: int = 80) -> list[dict[str, Any]]:
    linked_assistant_ids = _linked_assistant_event_ids(events)
    items = [
        _timeline_item(event)
        for event in events
        if event.kind in VISIBLE_KINDS and event.id not in linked_assistant_ids
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


def _summary_lines(item: TimelineItem) -> list[str]:
    header = f"{_time_label(item.time)} #{item.event_id}"
    who = item.who or "unknown"
    message = item.message or "(empty)"

    if item.kind == "group_message":
        lines = [f"{header} read {who}: {message}"]
        if item.decision or item.reason:
            lines.append(f"queue: {item.decision or 'observed'}{_reason_suffix(item.reason)}")
        return lines

    if item.kind == "loop_decision":
        lines = [f"{header} {who}: {message}"]
        lines.append(
            f"decision: {item.decision or 'unknown'}{_reason_suffix(item.reason)}; "
            f"send={_sent_label(item.sent)}"
        )
        if item.reply:
            lines.append(f"bot: {item.reply}")
        token_line = _token_line(item.tokens)
        if token_line:
            lines.append(token_line)
        web_line = _web_line(item.web)
        if web_line:
            lines.append(web_line)
        if item.trace_id:
            lines.append(f"trace: {item.trace_id}")
        return lines

    if item.kind in {"assistant_reply", "assistant_blocked", "assistant_placeholder"}:
        lines = [f"{header} bot: {item.reply or message}"]
        lines.append(
            f"assistant: {item.decision or _status(item)}{_reason_suffix(item.reason)}; "
            f"send={_sent_label(item.sent)}"
        )
        return lines

    if item.kind == "behavior_feedback":
        lines = [f"{header} feedback from {who}: {message}"]
        if item.reason:
            lines.append(f"score: {item.reason}")
        if item.reply:
            lines.append(f"recent bot: {item.reply}")
        return lines

    lines = [f"{header} {item.kind}: {message}"]
    if item.reason:
        lines.append(f"reason: {item.reason}")
    return lines


def _status(item: TimelineItem) -> str:
    if item.kind == "group_message":
        return item.decision or "observed"
    if item.kind == "loop_decision":
        if item.sent is True:
            return "sent"
        if item.decision:
            return item.decision
        if item.sent is False:
            return "not_sent"
        return "decision"
    if item.kind == "assistant_reply":
        return "sent" if item.sent is True else "reply"
    if item.kind == "assistant_placeholder":
        return "placeholder"
    if item.kind == "assistant_blocked":
        return "blocked"
    return item.decision or item.kind


def _token_line(tokens: dict[str, Any]) -> str:
    if not tokens:
        return ""
    parts: list[str] = []
    local = tokens.get("local") if isinstance(tokens.get("local"), dict) else {}
    api = tokens.get("api") if isinstance(tokens.get("api"), dict) else {}

    if _has_token_values(local, "prompt", "completion", "total"):
        parts.append(f"local={local.get('prompt', '?')}/{local.get('completion', '?')}/{local.get('total', '?')}")
    if _has_token_values(api, "input", "output", "total"):
        api_part = f"api={api.get('input', '?')}/{api.get('output', '?')}/{api.get('total', '?')}"
        if api.get("cached") is not None:
            api_part += f" cached={api.get('cached')}"
        if api.get("reasoning") is not None:
            api_part += f" reasoning={api.get('reasoning')}"
        parts.append(api_part)
    if not parts and _has_token_values(tokens, "prompt", "completion", "total"):
        parts.append(f"model={tokens.get('prompt', '?')}/{tokens.get('completion', '?')}/{tokens.get('total', '?')}")

    latency = tokens.get("latency_seconds") or local.get("latency_seconds") or api.get("latency_seconds")
    if latency is not None:
        parts.append(f"latency={latency}s")
    if tokens.get("thinking_level") is not None:
        parts.append(f"think={tokens.get('thinking_level')}")
    if tokens.get("completion_per_second") is not None:
        parts.append(f"tok/s={tokens.get('completion_per_second')}")
    return f"tokens: {' '.join(parts)}" if parts else ""


def _web_line(web: dict[str, Any]) -> str:
    if not web:
        return ""
    if not (web.get("used") or web.get("search_used") or web.get("query")):
        return ""
    query = _short(_text(web.get("query")), max_length=120)
    return (
        f"web: used={bool(web.get('used'))} search={bool(web.get('search_used'))} "
        f"sources={web.get('source_count', 0)} query={query}"
    ).rstrip()


def _has_token_values(source: dict[str, Any], *keys: str) -> bool:
    return any(source.get(key) is not None for key in keys)


def _reason_suffix(reason: str) -> str:
    return f" reason={reason}" if reason else ""


def _sent_label(value: bool | None) -> str:
    if value is True:
        return "sent"
    if value is False:
        return "not_sent"
    return "n/a"


def _time_label(value: str) -> str:
    text = _text(value)
    if len(text) >= 19 and text[10] == "T":
        return text[11:19]
    if len(text) >= 8 and text[2] == ":" and text[5] == ":":
        return text[:8]
    return text[:19]


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
