from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from typing import Any


@dataclass(frozen=True)
class EngagementSignals:
    topic_interest: float = 0.5
    interruption_risk: float = 0.5
    is_shared_context: bool = False
    is_direct_followup: bool = False
    memory_salience: str = "none"
    reason: str = ""

    @classmethod
    def from_gate_decision(cls, decision: dict[str, Any], *, direct_followup: bool = False) -> "EngagementSignals":
        return cls(
            topic_interest=_bounded_float(decision.get("topic_interest"), default=_interest_from_attention(decision)),
            interruption_risk=_bounded_float(
                decision.get("interruption_risk"),
                default=_risk_from_attention(decision),
            ),
            is_shared_context=bool(decision.get("is_shared_context", decision.get("attention") != "other_person")),
            is_direct_followup=bool(decision.get("is_direct_followup", direct_followup)),
            memory_salience=_choice(decision.get("memory_salience"), {"short", "long", "none"}, "none"),
            reason=str(decision.get("reason", "")).strip(),
        )

    def to_metadata(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EngagementDecision:
    action: str
    reason: str
    reply_probability: float
    roll: float | None
    directness: str
    continuation_budget: int
    factors: dict[str, float]
    signals: EngagementSignals

    def to_metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data["signals"] = self.signals.to_metadata()
        return data


class EngagementPolicy:
    def decide(
        self,
        *,
        activity: float,
        user_affinity: float,
        global_affinity: float,
        mood_label: str,
        mood_intensity: float,
        directness: str,
        signals: EngagementSignals,
        turn_key: str,
        model_action: str,
        model_reason: str,
    ) -> EngagementDecision:
        activity = _clamp(activity)
        user_affinity = _clamp(user_affinity, default=0.5)
        global_affinity = _clamp(global_affinity, default=0.5)
        mood_intensity = _clamp(mood_intensity)
        directness = directness or "ambient"

        if directness in {"direct_address", "reply_to_bot", "followup", "answer_required", "repair_required", "direct"}:
            return EngagementDecision(
                action="reply",
                reason=model_reason or directness,
                reply_probability=1.0,
                roll=None,
                directness=directness,
                continuation_budget=self._continuation_budget(
                    directness=directness,
                    affinity=user_affinity,
                    topic_interest=signals.topic_interest,
                    interruption_risk=signals.interruption_risk,
                ),
                factors=self._factors(
                    user_affinity=user_affinity,
                    global_affinity=global_affinity,
                    mood_label=mood_label,
                    mood_intensity=mood_intensity,
                    signals=signals,
                    directness=directness,
                ),
                signals=signals,
            )

        factors = self._factors(
            user_affinity=user_affinity,
            global_affinity=global_affinity,
            mood_label=mood_label,
            mood_intensity=mood_intensity,
            signals=signals,
            directness=directness,
        )
        probability = activity
        for value in factors.values():
            probability *= value
        probability = min(max(probability, 0.0), self._probability_cap(directness, signals))

        if model_action == "no_reply":
            probability *= 0.45
        roll = stable_roll(turn_key)
        action = "reply" if roll < probability else "no_reply"
        reason = model_reason or "engagement_policy"
        if action == "no_reply" and not reason:
            reason = "engagement_roll_below_threshold"

        return EngagementDecision(
            action=action,
            reason=reason,
            reply_probability=round(probability, 4),
            roll=round(roll, 4),
            directness=directness,
            continuation_budget=self._continuation_budget(
                directness=directness,
                affinity=user_affinity,
                topic_interest=signals.topic_interest,
                interruption_risk=signals.interruption_risk,
            ),
            factors=factors,
            signals=signals,
        )

    def spontaneous_target_per_hour(
        self,
        *,
        activity: float,
        global_affinity: float,
        mood_label: str,
        mood_intensity: float,
        context_interest: float,
    ) -> float:
        mood = self._mood_factor(mood_label, _clamp(mood_intensity))
        global_factor = 0.75 + 0.50 * _clamp(global_affinity, default=0.5)
        value = 2.0 * _clamp(activity) * global_factor * mood * _clamp(context_interest, default=0.5)
        return round(min(2.0, max(0.0, value)), 4)

    def spontaneous_probability(self, *, target_per_hour: float, interval_seconds: float) -> float:
        if target_per_hour <= 0 or interval_seconds <= 0:
            return 0.0
        return round(1.0 - math.exp(-target_per_hour * interval_seconds / 3600.0), 4)

    def _factors(
        self,
        *,
        user_affinity: float,
        global_affinity: float,
        mood_label: str,
        mood_intensity: float,
        signals: EngagementSignals,
        directness: str,
    ) -> dict[str, float]:
        return {
            "affinity": round(0.55 + 0.90 * user_affinity, 4),
            "global": round(0.75 + 0.50 * global_affinity, 4),
            "mood": round(self._mood_factor(mood_label, mood_intensity), 4),
            "topic": round(0.60 + 0.90 * _clamp(signals.topic_interest, default=0.5), 4),
            "momentum": round(self._momentum_factor(directness, signals), 4),
            "interruption": round(1.0 - 0.80 * _clamp(signals.interruption_risk, default=0.5), 4),
        }

    def _mood_factor(self, label: str, intensity: float) -> float:
        normalized = (label or "neutral").casefold()
        if normalized in {"playful", "curious", "upbeat", "warm"}:
            return 1.0 + 0.25 * intensity
        if normalized in {"guarded", "irritated", "angry"}:
            return 1.0 - 0.40 * intensity
        if normalized in {"tired", "sad", "low"}:
            return 1.0 - 0.25 * intensity
        return 1.0

    def _momentum_factor(self, directness: str, signals: EngagementSignals) -> float:
        if signals.is_direct_followup:
            return 1.25
        if directness == "likely_other_conversation":
            return 0.35
        if signals.is_shared_context:
            return 1.10
        return 0.75

    def _probability_cap(self, directness: str, signals: EngagementSignals) -> float:
        if directness == "likely_other_conversation":
            return 0.08 if signals.topic_interest < 0.85 or signals.interruption_risk > 0.2 else 0.35
        if signals.interruption_risk >= 0.8:
            return 0.15
        return 0.85

    def _continuation_budget(
        self,
        *,
        directness: str,
        affinity: float,
        topic_interest: float,
        interruption_risk: float,
    ) -> int:
        if interruption_risk >= 0.75:
            return 0
        if directness in {"direct_address", "reply_to_bot", "followup", "answer_required", "repair_required", "direct"}:
            if affinity >= 0.85 and topic_interest >= 0.7:
                return 3
            if affinity >= 0.65 or topic_interest >= 0.7:
                return 2
            return 1
        if affinity >= 0.9 and topic_interest >= 0.8:
            return 2
        if affinity >= 0.75 and topic_interest >= 0.6:
            return 1
        return 0


def stable_roll(key: str) -> float:
    digest = hashlib.sha256(key.encode("utf-8", errors="ignore")).digest()
    value = int.from_bytes(digest[:8], "big")
    return value / float(2**64 - 1)


def _interest_from_attention(decision: dict[str, Any]) -> float:
    attention = str(decision.get("attention", "")).strip().casefold()
    if attention in {"direct", "followup"}:
        return 0.9
    if attention == "ambient":
        return _bounded_float(decision.get("attention_score"), default=0.5)
    if attention == "other_person":
        return 0.2
    return 0.5


def _risk_from_attention(decision: dict[str, Any]) -> float:
    attention = str(decision.get("attention", "")).strip().casefold()
    if attention in {"direct", "followup"}:
        return 0.05
    if attention == "other_person":
        return 0.9
    return 0.35


def _bounded_float(value: Any, *, default: float) -> float:
    return _clamp(value, default=default)


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def _choice(value: Any, choices: set[str], default: str) -> str:
    text = str(value or "").strip().casefold()
    return text if text in choices else default
