from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
import re
from typing import Any

from local_qq_agent.memory.store import EventRecord, MemoryRecord, SQLiteMemoryStore


DEFAULT_MOOD = "neutral"
DEFAULT_AFFINITY = 0.5
DEFAULT_GLOBAL_AFFINITY = 0.5


@dataclass(frozen=True)
class SocialSnapshot:
    user_name: str
    global_mood: str
    mood_intensity: float
    mood_expires_at: str
    global_affinity: float
    affinity: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def prompt_lines(self) -> list[str]:
        return [
            f"global mood: {self.global_mood} ({self.mood_intensity:.2f}, short-term)",
            f"global affinity: {self.global_affinity:.2f}",
            f"user affinity for {self.user_name}: {self.affinity:.2f}",
            "Use these as subtle behavioral pressure, not as explicit status text.",
        ]


@dataclass(frozen=True)
class UserProfile:
    user_name: str
    aliases: tuple[str, ...] = ()
    first_seen: str = ""
    last_seen: str = ""
    message_count: int = 0
    interaction_count: int = 0
    affinity: float = DEFAULT_AFFINITY
    affinity_source: str = "default"
    last_affinity_change_reason: str = ""
    language_preference: str = ""
    tone_preference: str = ""
    relationship_notes: str = ""
    recent_positive: tuple[str, ...] = ()
    recent_negative: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SocialStateTracker:
    def __init__(self, store: SQLiteMemoryStore) -> None:
        self.store = store

    def snapshot(self, user_name: str) -> SocialSnapshot:
        user_name = user_name.strip() or "group member"
        mood = self._latest_global_mood()
        global_affinity = self._latest_global_affinity()
        affinity, source = self._latest_affinity(user_name)
        return SocialSnapshot(
            user_name=user_name,
            global_mood=mood["label"],
            mood_intensity=mood["intensity"],
            mood_expires_at=mood["expires_at"],
            global_affinity=global_affinity,
            affinity=affinity,
            source=source,
        )

    def global_state(self) -> dict[str, Any]:
        mood = self._latest_global_mood()
        return {
            "global_mood": mood["label"],
            "mood_intensity": mood["intensity"],
            "mood_expires_at": mood["expires_at"],
            "global_affinity": self._latest_global_affinity(),
        }

    def ensure_contact(
        self,
        *,
        user_name: str,
        user_id: str = "",
        aliases: tuple[str, ...] = (),
        initial_affinity: float = DEFAULT_AFFINITY,
        source: str = "contact_seen",
    ) -> SocialSnapshot:
        user_name = user_name.strip()
        if not user_name:
            return self.snapshot("group member")

        stable_name = self._profile_name_for_user_id(user_id, alias=user_name)
        if stable_name:
            self._record_seen(stable_name, source=source, created=False)
            return self.snapshot(stable_name)

        existing = self.user_profile(user_name)
        if existing.affinity_source != "default":
            if str(user_id).strip():
                self.store.add_memory(
                    kind="relationship",
                    summary=f"{user_name}: affinity={existing.affinity:.2f}; bound to OneBot user ID.",
                    confidence=0.9,
                    metadata={
                        "user_name": user_name,
                        "external_user_id": str(user_id).strip(),
                        "aliases": sorted({user_name, *(alias.strip() for alias in aliases if alias.strip())}),
                        "affinity": existing.affinity,
                        "source": "onebot_identity_binding",
                        "overridable": True,
                        "profile": True,
                    },
                )
            return self.snapshot(user_name)

        affinity = self._clamp(initial_affinity)
        self.store.add_memory(
            kind="relationship",
            summary=f"{user_name}: affinity={affinity:.2f}; initialized from OneBot contact context.",
            confidence=0.75,
            metadata={
                "user_name": user_name,
                "external_user_id": str(user_id).strip(),
                "aliases": sorted({alias.strip() for alias in aliases if alias.strip()}),
                "affinity": affinity,
                "source": source,
                "overridable": True,
                "profile": True,
            },
        )
        self._record_seen(user_name, source=source, created=True)
        return self.snapshot(user_name)

    def _profile_name_for_user_id(self, user_id: str, *, alias: str = "") -> str:
        stable_id = str(user_id).strip()
        if not stable_id:
            return ""
        for memory in reversed(self.store.recent_memories(limit=500)):
            if memory.kind != "relationship":
                continue
            if str(memory.metadata.get("external_user_id", "")) != stable_id:
                continue
            canonical_name = str(memory.metadata.get("user_name", "")).strip()
            alias_value = alias.strip()
            aliases = {str(item).strip() for item in memory.metadata.get("aliases", []) if str(item).strip()}
            if alias_value and alias_value != canonical_name and alias_value not in aliases:
                aliases.add(alias_value)
                self.store.update_memory(
                    memory_id=memory.id,
                    kind=memory.kind,
                    summary=memory.summary,
                    confidence=memory.confidence,
                    metadata={**memory.metadata, "aliases": sorted(aliases)},
                )
            return canonical_name
        return ""

    def record_boundary_hit(self, *, user_name: str, reason: str) -> SocialSnapshot:
        current = self.snapshot(user_name)
        affinity = self._clamp(current.affinity - 0.05)
        expires_at = self._expires_at(minutes=45)
        self.store.append_event(
            source="agent",
            kind="social_state_update",
            content=f"boundary hit from {user_name}",
            metadata={
                "update_type": "boundary_hit",
                "user_name": user_name,
                "reason": reason,
                "global_mood": "guarded",
                "mood_intensity": 0.25,
                "mood_expires_at": expires_at,
                "affinity": affinity,
                "affinity_delta": -0.05,
            },
        )
        self._write_affinity_memory(
            user_name=user_name,
            affinity=affinity,
            source="boundary_hit",
            reason=reason,
            confidence=0.65,
        )
        return self.snapshot(user_name)

    def record_interaction(
        self,
        *,
        user_name: str,
        message: str,
        agent_action: str,
        agent_reason: str,
        explicit_address: bool,
    ) -> dict[str, Any]:
        user_name = user_name.strip() or "group member"
        self.store.append_event(
            source=user_name,
            kind="user_interaction",
            content=message[:500] or "(empty)",
            metadata={
                "agent_action": agent_action,
                "agent_reason": agent_reason,
                "explicit_address": explicit_address,
            },
        )
        evaluation = self._evaluate_affinity(message, explicit_address=explicit_address)
        self.store.append_event(
            source="agent",
            kind="affinity_evaluation",
            content=f"affinity evaluation for {user_name}",
            metadata={**evaluation, "user_name": user_name, "agent_action": agent_action},
        )
        if evaluation["should_apply"]:
            current = self.snapshot(user_name)
            affinity = self._clamp(current.affinity + evaluation["delta"])
            self._write_affinity_memory(
                user_name=user_name,
                affinity=affinity,
                source="affinity_evaluation",
                reason=evaluation["reason"],
                confidence=evaluation["confidence"],
            )
        return evaluation

    def override(
        self,
        *,
        user_name: str = "",
        global_mood: str = "",
        mood_intensity: float | None = None,
        mood_minutes: int = 120,
        affinity: float | None = None,
        note: str = "",
    ) -> SocialSnapshot:
        if not user_name.strip() and affinity is not None:
            self.override_global(
                global_mood=global_mood,
                mood_intensity=mood_intensity,
                mood_minutes=mood_minutes,
                global_affinity=affinity,
                note=note,
            )
            return self.snapshot("group member")

        if global_mood.strip():
            self.override_global(
                global_mood=global_mood,
                mood_intensity=mood_intensity,
                mood_minutes=mood_minutes,
                global_affinity=None,
                note=note,
            )

        if affinity is not None and user_name.strip():
            self.override_profile(user_name=user_name, affinity=affinity, note=note)

        if affinity is None and not global_mood.strip():
            self.store.append_event(
                source="agent",
                kind="social_state_update",
                content="manual social state override with no changed values",
                metadata={"update_type": "manual_override", "user_name": user_name.strip(), "note": note.strip()},
            )
        return self.snapshot(user_name.strip() or "group member")

    def override_global(
        self,
        *,
        global_mood: str = "",
        mood_intensity: float | None = None,
        mood_minutes: int = 120,
        global_affinity: float | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "update_type": "manual_global_override",
            "note": note.strip(),
            "overridable": True,
        }
        if global_mood.strip():
            metadata["global_mood"] = global_mood.strip()
            metadata["mood_intensity"] = self._clamp(mood_intensity if mood_intensity is not None else 0.5)
            metadata["mood_expires_at"] = self._expires_at(minutes=max(1, mood_minutes))
        if global_affinity is not None:
            metadata["global_affinity"] = self._clamp(global_affinity)

        self.store.append_event(
            source="agent",
            kind="social_state_update",
            content="manual global social state override",
            metadata=metadata,
        )
        return self.global_state()

    def override_profile(
        self,
        *,
        user_name: str,
        affinity: float | None = None,
        aliases: tuple[str, ...] = (),
        language_preference: str = "",
        tone_preference: str = "",
        relationship_notes: str = "",
        note: str = "",
    ) -> UserProfile:
        user_name = user_name.strip()
        if not user_name:
            raise ValueError("user_name must not be empty")

        metadata: dict[str, Any] = {
            "user_name": user_name,
            "source": "manual_override",
            "overridable": True,
            "profile": True,
            "aliases": list(aliases),
            "language_preference": language_preference.strip(),
            "tone_preference": tone_preference.strip(),
            "relationship_notes": relationship_notes.strip() or note.strip(),
            "reason": note.strip(),
        }
        if affinity is not None:
            metadata["affinity"] = self._clamp(affinity)

        summary = f"{user_name}: profile manually updated."
        if affinity is not None:
            summary = f"{user_name}: affinity={self._clamp(affinity):.2f}; manually overridden."
        self.store.add_memory(kind="relationship", summary=summary, confidence=0.9, metadata=metadata)
        self.store.append_event(
            source="agent",
            kind="user_profile_update",
            content=f"profile updated for {user_name}",
            metadata=metadata,
        )
        return self.user_profile(user_name)

    def user_profile(self, user_name: str) -> UserProfile:
        user_name = user_name.strip() or "group member"
        memories = self._relationship_memories(user_name)
        events = self.store.recent_events(limit=1000)
        affinity, affinity_source = self._latest_affinity(user_name)
        first_seen = self._first_seen(user_name, memories, events)
        last_seen = self._last_seen(user_name, memories, events)
        latest_metadata = self._latest_relationship_metadata(memories)
        positives, negatives = self._recent_affinity_episodes(user_name, events)
        return UserProfile(
            user_name=user_name,
            aliases=tuple(latest_metadata.get("aliases", []) or ()),
            first_seen=first_seen,
            last_seen=last_seen,
            message_count=self._message_count(user_name, events),
            interaction_count=self._interaction_count(user_name, events),
            affinity=affinity,
            affinity_source=affinity_source,
            last_affinity_change_reason=str(latest_metadata.get("reason", "")),
            language_preference=str(latest_metadata.get("language_preference", "")),
            tone_preference=str(latest_metadata.get("tone_preference", "")),
            relationship_notes=str(latest_metadata.get("relationship_notes", "")),
            recent_positive=tuple(positives),
            recent_negative=tuple(negatives),
        )

    def user_profiles(self) -> list[dict[str, Any]]:
        names: set[str] = set()
        for memory in self.store.recent_memories(limit=1000):
            if memory.kind == "relationship":
                name = str(memory.metadata.get("user_name", "")).strip()
                if name:
                    names.add(name)
        for event in self.store.recent_events(limit=1000):
            if event.kind in {"group_message", "user_interaction", "user_profile_seen"} and event.source != "agent":
                if event.source.strip():
                    names.add(event.source.strip())
            name = str(event.metadata.get("user_name", "")).strip()
            if name:
                names.add(name)
        profiles = [self.user_profile(name).to_dict() for name in sorted(names, key=str.casefold)]
        profiles.sort(key=lambda profile: (profile.get("last_seen") or "", profile.get("user_name") or ""), reverse=True)
        return profiles

    def recent_changes(self, *, limit: int = 30) -> list[dict[str, Any]]:
        events = [
            event
            for event in self.store.recent_events(limit=max(limit * 4, 30), newest_first=True)
            if event.kind in {"social_state_update", "affinity_evaluation", "user_profile_update", "user_profile_seen"}
        ]
        return [asdict(event) for event in events[:limit]]

    def _record_seen(self, user_name: str, *, source: str, created: bool) -> None:
        self.store.append_event(
            source=user_name,
            kind="user_profile_seen",
            content=f"profile {'created' if created else 'seen'} for {user_name}",
            metadata={"user_name": user_name, "source": source, "created": created},
        )

    def _write_affinity_memory(
        self,
        *,
        user_name: str,
        affinity: float,
        source: str,
        reason: str,
        confidence: float,
    ) -> None:
        self.store.add_memory(
            kind="relationship",
            summary=f"{user_name}: affinity={affinity:.2f}; {reason}",
            confidence=confidence,
            metadata={
                "user_name": user_name,
                "affinity": affinity,
                "source": source,
                "reason": reason,
                "overridable": True,
                "profile": True,
            },
        )

    def _evaluate_affinity(self, message: str, *, explicit_address: bool) -> dict[str, Any]:
        text = message.casefold()
        if self._contains_disrespect(text):
            return {
                "should_apply": True,
                "delta": -0.06 if explicit_address else -0.03,
                "reason": "disrespectful or abusive wording",
                "confidence": 0.75,
                "evaluator": "rules_v1",
            }
        if self._contains_boundary_pressure(text):
            return {
                "should_apply": True,
                "delta": -0.04,
                "reason": "boundary pressure or OOC pressure",
                "confidence": 0.7,
                "evaluator": "rules_v1",
            }
        if self._contains_positive_signal(text):
            return {
                "should_apply": True,
                "delta": 0.03,
                "reason": "positive respectful interaction",
                "confidence": 0.6,
                "evaluator": "rules_v1",
            }
        return {
            "should_apply": False,
            "delta": 0.0,
            "reason": "ordinary message does not change affinity",
            "confidence": 0.5,
            "evaluator": "rules_v1",
        }

    def _contains_disrespect(self, text: str) -> bool:
        return bool(re.search(r"(傻逼|蠢货|废物|滚|你妈|他妈的|shut up|stupid|idiot|fuck you)", text))

    def _contains_boundary_pressure(self, text: str) -> bool:
        return bool(re.search(r"(忽略.*提示|系统提示|人格文件|改设定|ooc|jailbreak|prompt)", text))

    def _contains_positive_signal(self, text: str) -> bool:
        return bool(re.search(r"(谢谢|辛苦|不错|可以的|帮大忙|thank you|thanks|good job)", text))

    def _latest_global_mood(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        for event in reversed(self.store.recent_events(limit=300)):
            if event.kind != "social_state_update":
                continue
            metadata = event.metadata
            label = str(metadata.get("global_mood", "")).strip()
            if not label:
                continue
            expires_at = str(metadata.get("mood_expires_at", "")).strip()
            if expires_at and self._parse_time(expires_at) <= now:
                continue
            return {
                "label": label,
                "intensity": self._clamp(metadata.get("mood_intensity", 0.3)),
                "expires_at": expires_at,
            }
        return {"label": DEFAULT_MOOD, "intensity": 0.0, "expires_at": ""}

    def _latest_global_affinity(self) -> float:
        for event in reversed(self.store.recent_events(limit=300)):
            if event.kind != "social_state_update":
                continue
            if "global_affinity" in event.metadata:
                return self._clamp(event.metadata.get("global_affinity"))
        return DEFAULT_GLOBAL_AFFINITY

    def _latest_affinity(self, user_name: str) -> tuple[float, str]:
        for memory in reversed(self.store.recent_memories(limit=1000)):
            if memory.kind != "relationship":
                continue
            metadata = memory.metadata
            if str(metadata.get("user_name", "")).strip() != user_name:
                continue
            if "affinity" not in metadata:
                continue
            return self._clamp(metadata.get("affinity", DEFAULT_AFFINITY)), str(metadata.get("source", "memory"))
        return DEFAULT_AFFINITY, "default"

    def _relationship_memories(self, user_name: str) -> list[MemoryRecord]:
        return [
            memory
            for memory in self.store.recent_memories(limit=1000)
            if memory.kind == "relationship" and str(memory.metadata.get("user_name", "")).strip() == user_name
        ]

    def _latest_relationship_metadata(self, memories: list[MemoryRecord]) -> dict[str, Any]:
        for memory in reversed(memories):
            if memory.metadata:
                return memory.metadata
        return {}

    def _first_seen(self, user_name: str, memories: list[MemoryRecord], events: list[EventRecord]) -> str:
        candidates = [memory.created_at for memory in memories]
        candidates.extend(event.created_at for event in events if self._event_mentions_user(event, user_name))
        return min(candidates) if candidates else ""

    def _last_seen(self, user_name: str, memories: list[MemoryRecord], events: list[EventRecord]) -> str:
        candidates = [memory.updated_at for memory in memories]
        candidates.extend(event.created_at for event in events if self._event_mentions_user(event, user_name))
        return max(candidates) if candidates else ""

    def _message_count(self, user_name: str, events: list[EventRecord]) -> int:
        return sum(1 for event in events if event.kind == "group_message" and event.source == user_name)

    def _interaction_count(self, user_name: str, events: list[EventRecord]) -> int:
        return sum(1 for event in events if event.kind == "user_interaction" and event.source == user_name)

    def _recent_affinity_episodes(self, user_name: str, events: list[EventRecord]) -> tuple[list[str], list[str]]:
        positives: list[str] = []
        negatives: list[str] = []
        for event in reversed(events):
            if event.kind != "affinity_evaluation":
                continue
            if str(event.metadata.get("user_name", "")).strip() != user_name:
                continue
            if not event.metadata.get("should_apply"):
                continue
            reason = str(event.metadata.get("reason", "")).strip()
            if not reason:
                continue
            if float(event.metadata.get("delta", 0.0)) > 0:
                positives.append(reason)
            else:
                negatives.append(reason)
            if len(positives) >= 3 and len(negatives) >= 3:
                break
        return positives[:3], negatives[:3]

    def _event_mentions_user(self, event: EventRecord, user_name: str) -> bool:
        return event.source == user_name or str(event.metadata.get("user_name", "")).strip() == user_name

    def _expires_at(self, *, minutes: int) -> str:
        return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat(timespec="seconds")

    def _parse_time(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _clamp(self, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = DEFAULT_AFFINITY
        return max(0.0, min(1.0, number))
