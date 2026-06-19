from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from local_qq_agent.memory import SQLiteMemoryStore
from local_qq_agent.paths import ensure_parent
from local_qq_agent.agent.style_learning import summarize_style_learning


TRAINING_EVENT_KINDS = {
    "group_message",
    "assistant_reply",
    "assistant_blocked",
    "assistant_placeholder",
    "behavior_feedback",
    "memory_added",
    "memory_deleted",
    "loop_decision",
}


@dataclass(frozen=True)
class RunSessionLog:
    created_at: str
    style_learning_target_user: str
    source_event_start_exclusive: int
    source_event_count: int
    event_count: int
    events: list[dict[str, Any]]
    style_learning: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunSessionLogExporter:
    def __init__(self, store: SQLiteMemoryStore) -> None:
        self.store = store

    def build(
        self,
        *,
        started_after_event_id: int,
        style_learning_target_user: str = "",
        max_events: int = 2000,
    ) -> RunSessionLog:
        events = self.store.events_since(started_after_event_id, limit=max_events)
        clean_events = [_clean_event(asdict(event)) for event in events if event.kind in TRAINING_EVENT_KINDS]
        clean_events = [event for event in clean_events if event]
        style_learning = summarize_style_learning(
            clean_events,
            target_user=style_learning_target_user,
        ).to_dict()
        return RunSessionLog(
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            style_learning_target_user=style_learning_target_user,
            source_event_start_exclusive=started_after_event_id,
            source_event_count=len(events),
            event_count=len(clean_events),
            events=clean_events,
            style_learning=style_learning,
        )

    def export(
        self,
        *,
        started_after_event_id: int,
        output_dir: Path,
        style_learning_target_user: str = "",
        max_events: int = 2000,
    ) -> dict[str, Any]:
        run_log = self.build(
            started_after_event_id=started_after_event_id,
            style_learning_target_user=style_learning_target_user,
            max_events=max_events,
        )
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"run_log_{timestamp}.json"
        ensure_parent(path)
        path.write_text(json.dumps(run_log.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "path": str(path),
            "event_count": run_log.event_count,
            "source_event_count": run_log.source_event_count,
            "style_learning": run_log.style_learning,
        }


def export_clean_run_log(
    *,
    store: SQLiteMemoryStore,
    started_after_event_id: int,
    output_dir: Path,
    style_learning_target_user: str = "",
    max_events: int = 2000,
) -> dict[str, Any]:
    return RunSessionLogExporter(store).export(
        started_after_event_id=started_after_event_id,
        output_dir=output_dir,
        style_learning_target_user=style_learning_target_user,
        max_events=max_events,
    )


def _clean_event(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    kind = str(event.get("kind", ""))

    if kind == "group_message":
        text = str(metadata.get("clean_text") or event.get("content") or "").strip()
        if not text:
            return {}
        return {
            "id": event.get("id"),
            "time": event.get("created_at"),
            "kind": kind,
            "sender": metadata.get("sender_name") or event.get("source"),
            "text": text,
            "agent_action": metadata.get("agent_action"),
            "agent_reason": metadata.get("agent_reason"),
            "references_bot": metadata.get("references_bot"),
        }

    if kind in {"assistant_reply", "assistant_blocked", "assistant_placeholder"}:
        return {
            "id": event.get("id"),
            "time": event.get("created_at"),
            "kind": kind,
            "text": event.get("content"),
            "reason": metadata.get("reason"),
            "reply_to": metadata.get("user_name") or metadata.get("sender_name"),
            "thinking_level": metadata.get("thinking_level"),
            "web_used": metadata.get("web_used"),
        }

    if kind == "loop_decision":
        return {
            "id": event.get("id"),
            "time": event.get("created_at"),
            "kind": kind,
            "sender": metadata.get("sender_name"),
            "message": metadata.get("message_text"),
            "action": metadata.get("action"),
            "reason": metadata.get("reason"),
            "sent": metadata.get("sent"),
            "send_reason": metadata.get("send_reason"),
            "elapsed_seconds": metadata.get("elapsed_seconds"),
        }

    if kind == "behavior_feedback":
        return {
            "id": event.get("id"),
            "time": event.get("created_at"),
            "kind": kind,
            "score": metadata.get("score_value"),
            "note": metadata.get("score_note"),
            "classification": metadata.get("classification"),
            "recent_reply": metadata.get("recent_reply"),
            "summary": event.get("content"),
        }

    return {
        "id": event.get("id"),
        "time": event.get("created_at"),
        "kind": kind,
        "text": event.get("content"),
    }
