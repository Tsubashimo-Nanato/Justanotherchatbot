from __future__ import annotations

from local_qq_agent.memory.store import EventRecord


def after_session_start(event: EventRecord, min_event_id: int = 0) -> bool:
    return event.id > max(0, int(min_event_id))


def is_runtime_group_message(event: EventRecord, *, min_event_id: int = 0, include_api_events: bool = False) -> bool:
    if event.kind != "group_message":
        return False
    if not after_session_start(event, min_event_id):
        return False
    metadata = event.metadata or {}
    origin = metadata.get("origin")
    if min_event_id <= 0 and origin is None:
        return True
    allowed_origins = {"qq_loop"}
    if include_api_events:
        allowed_origins.add("api")
    if origin not in allowed_origins:
        return False
    return metadata.get("agent_action") in {"reply", "no_reply", "context_only", "queued", "aggregating"}


def is_runtime_agent_reply(event: EventRecord, *, min_event_id: int = 0, include_api_events: bool = False) -> bool:
    if not after_session_start(event, min_event_id):
        return False
    if event.kind == "loop_decision":
        return bool(str((event.metadata or {}).get("agent_reply") or "").strip())
    if event.kind in {"assistant_reply", "assistant_blocked", "assistant_placeholder"}:
        origin = (event.metadata or {}).get("origin")
        if origin == "qq_loop" or (min_event_id <= 0 and origin is None):
            return True
        return include_api_events and origin == "api"
    return False


def is_runtime_conversation_event(event: EventRecord, *, min_event_id: int = 0, include_api_events: bool = False) -> bool:
    return is_runtime_group_message(
        event,
        min_event_id=min_event_id,
        include_api_events=include_api_events,
    ) or is_runtime_agent_reply(
        event,
        min_event_id=min_event_id,
        include_api_events=include_api_events,
    )
