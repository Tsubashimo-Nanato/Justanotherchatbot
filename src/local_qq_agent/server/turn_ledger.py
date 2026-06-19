from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any


ACTIVE_STATES = {"queued", "inflight"}
CLOSED_STATES = {"completed", "suppressed", "context_only"}
KNOWN_STATES = {"observed", *ACTIVE_STATES, *CLOSED_STATES}


@dataclass
class TurnRecord:
    canonical_turn_id: str
    sender: str
    clean_text: str
    raw_text: str
    references_bot: bool
    state: str
    created_at: float
    updated_at: float
    raw_fingerprint_aliases: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    wait_attempted: bool = False
    wait_sent: bool = False
    answer_attempted: bool = False
    answer_sent: bool = False
    response_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_turn_id": self.canonical_turn_id,
            "sender": self.sender,
            "clean_text": self.clean_text,
            "raw_text": self.raw_text,
            "references_bot": self.references_bot,
            "state": self.state,
            "created_at": round(self.created_at, 3),
            "updated_at": round(self.updated_at, 3),
            "raw_fingerprint_aliases": sorted(self.raw_fingerprint_aliases),
            "metadata": dict(self.metadata),
            "response": {
                "wait_attempted": self.wait_attempted,
                "wait_sent": self.wait_sent,
                "answer_attempted": self.answer_attempted,
                "answer_sent": self.answer_sent,
                **dict(self.response_metadata),
            },
        }


class TurnLedger:
    def __init__(self, *, ttl_seconds: float = 3600.0) -> None:
        self.ttl_seconds = max(ttl_seconds, 120.0)
        self._records: dict[str, TurnRecord] = {}
        self._alias_to_turn_id: dict[str, str] = {}

    def observe(
        self,
        *,
        turn_id: str,
        sender: str,
        clean_text: str,
        raw_text: str,
        fingerprint: str,
        references_bot: bool,
        metadata: dict[str, Any] | None = None,
    ) -> TurnRecord:
        self.prune()
        canonical_id = self._alias_to_turn_id.get(fingerprint, turn_id)
        now = time.time()
        record = self._records.get(canonical_id)
        if record is None:
            record = TurnRecord(
                canonical_turn_id=canonical_id,
                sender=sender,
                clean_text=clean_text,
                raw_text=raw_text,
                references_bot=references_bot,
                state="observed",
                created_at=now,
                updated_at=now,
                metadata=metadata or {},
            )
            self._records[canonical_id] = record
        else:
            record.updated_at = now
            if raw_text and raw_text != record.raw_text:
                record.metadata["latest_raw_text"] = raw_text
            if metadata:
                record.metadata.update(metadata)

        self.add_alias(canonical_id, fingerprint)
        if canonical_id != turn_id:
            self._alias_to_turn_id[turn_id] = canonical_id
        return record

    def add_alias(self, turn_id: str, fingerprint: str) -> None:
        if not turn_id or not fingerprint:
            return
        canonical_id = self._alias_to_turn_id.get(turn_id, turn_id)
        record = self._records.get(canonical_id)
        if record is None:
            return
        record.raw_fingerprint_aliases.add(fingerprint)
        self._alias_to_turn_id[fingerprint] = canonical_id
        self._alias_to_turn_id[turn_id] = canonical_id

    def can_enqueue(self, turn_id: str, fingerprint: str = "") -> bool:
        record = self.record_for(turn_id, fingerprint)
        if record is None:
            return True
        return record.state not in ACTIVE_STATES and record.state not in CLOSED_STATES

    def is_active_or_closed(self, turn_id: str, fingerprint: str = "") -> bool:
        record = self.record_for(turn_id, fingerprint)
        if record is None:
            return False
        return record.state in ACTIVE_STATES or record.state in CLOSED_STATES

    def is_closed(self, turn_id: str, fingerprint: str = "") -> bool:
        record = self.record_for(turn_id, fingerprint)
        if record is None:
            return False
        return record.state in CLOSED_STATES

    def is_active(self, turn_id: str, fingerprint: str = "") -> bool:
        record = self.record_for(turn_id, fingerprint)
        if record is None:
            return False
        return record.state in ACTIVE_STATES

    def mark_queued(self, turn_id: str, *, metadata: dict[str, Any] | None = None) -> None:
        self._set_state(turn_id, "queued", metadata=metadata)

    def mark_inflight(self, turn_id: str, *, metadata: dict[str, Any] | None = None) -> None:
        self._set_state(turn_id, "inflight", metadata=metadata)

    def mark_completed(self, turn_id: str, *, metadata: dict[str, Any] | None = None) -> None:
        self._set_state(turn_id, "completed", metadata=metadata)

    def mark_suppressed(self, turn_id: str, *, metadata: dict[str, Any] | None = None) -> None:
        self._set_state(turn_id, "suppressed", metadata=metadata)

    def mark_context_only(self, turn_id: str, *, metadata: dict[str, Any] | None = None) -> None:
        self._set_state(turn_id, "context_only", metadata=metadata)

    def can_send_wait(self, turn_id: str, fingerprint: str = "") -> bool:
        record = self.record_for(turn_id, fingerprint)
        if record is None:
            return True
        return not record.wait_attempted and not record.answer_attempted

    def mark_wait_attempted(
        self,
        turn_id: str,
        *,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record = self._record_or_create(turn_id)
        record.wait_attempted = True
        record.updated_at = time.time()
        record.response_metadata["wait_text"] = text
        if metadata:
            record.response_metadata["wait_metadata"] = dict(metadata)

    def mark_wait_result(
        self,
        turn_id: str,
        *,
        sent: bool,
        result: dict[str, Any] | None = None,
    ) -> None:
        record = self._record_or_create(turn_id)
        record.wait_attempted = True
        record.wait_sent = bool(sent)
        record.updated_at = time.time()
        record.response_metadata["wait_result"] = dict(result or {})

    def can_send_answer(self, turn_id: str, fingerprint: str = "") -> bool:
        record = self.record_for(turn_id, fingerprint)
        if record is None:
            return True
        return not record.answer_attempted

    def mark_answer_result(
        self,
        turn_id: str,
        *,
        sent: bool,
        result: dict[str, Any] | None = None,
        text: str = "",
    ) -> None:
        record = self._record_or_create(turn_id)
        record.answer_attempted = True
        record.answer_sent = bool(sent)
        record.updated_at = time.time()
        if text:
            record.response_metadata["answer_text"] = text
        record.response_metadata["answer_result"] = dict(result or {})

    def record_for(self, turn_id: str, fingerprint: str = "") -> TurnRecord | None:
        self.prune()
        for key in (fingerprint, turn_id):
            if not key:
                continue
            canonical_id = self._alias_to_turn_id.get(key, key)
            record = self._records.get(canonical_id)
            if record is not None:
                return record
        return None

    def summary(self) -> dict[str, Any]:
        self.prune()
        counts = {state: 0 for state in KNOWN_STATES}
        response_counts = {
            "wait_attempted": 0,
            "wait_sent": 0,
            "answer_attempted": 0,
            "answer_sent": 0,
        }
        for record in self._records.values():
            counts[record.state] = counts.get(record.state, 0) + 1
            for key in response_counts:
                if bool(getattr(record, key)):
                    response_counts[key] += 1
        recent = sorted(self._records.values(), key=lambda item: item.updated_at, reverse=True)[:20]
        return {
            "counts": counts,
            "response_counts": response_counts,
            "record_count": len(self._records),
            "alias_count": len(self._alias_to_turn_id),
            "recent": [record.to_dict() for record in recent],
        }

    def active_ids(self, state: str | None = None) -> list[str]:
        self.prune()
        records = self._records.values()
        if state is not None:
            records = [record for record in records if record.state == state]
        else:
            records = [record for record in records if record.state in ACTIVE_STATES]
        return sorted(record.canonical_turn_id for record in records)

    def clear_active(self) -> None:
        for record in self._records.values():
            if record.state in ACTIVE_STATES:
                record.state = "observed"
                record.updated_at = time.time()

    def prune(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        stale_ids = [
            turn_id
            for turn_id, record in self._records.items()
            if record.updated_at < cutoff and record.state not in ACTIVE_STATES
        ]
        if not stale_ids:
            return
        stale_set = set(stale_ids)
        for turn_id in stale_ids:
            self._records.pop(turn_id, None)
        self._alias_to_turn_id = {
            alias: turn_id for alias, turn_id in self._alias_to_turn_id.items() if turn_id not in stale_set
        }

    def _set_state(self, turn_id: str, state: str, *, metadata: dict[str, Any] | None = None) -> None:
        if state not in KNOWN_STATES:
            raise ValueError(f"unsupported turn state: {state}")
        record = self._record_or_create(turn_id)
        record.state = state
        record.updated_at = time.time()
        if metadata:
            record.metadata.update(metadata)

    def _record_or_create(self, turn_id: str) -> TurnRecord:
        canonical_id = self._alias_to_turn_id.get(turn_id, turn_id)
        record = self._records.get(canonical_id)
        if record is not None:
            return record

        now = time.time()
        record = TurnRecord(
            canonical_turn_id=canonical_id,
            sender="",
            clean_text="",
            raw_text="",
            references_bot=False,
            state="observed",
            created_at=now,
            updated_at=now,
        )
        self._records[canonical_id] = record
        self._alias_to_turn_id[turn_id] = canonical_id
        return record
