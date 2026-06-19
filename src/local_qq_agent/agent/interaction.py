from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


@dataclass(frozen=True)
class InteractionPlan:
    mode: str
    hook_budget: int
    affinity: float
    directness: str
    message_kind: str
    reason: str

    def to_metadata(self) -> dict[str, Any]:
        return asdict(self)

    def prompt_lines(self) -> list[str]:
        lines = [
            f"interaction_mode: {self.mode}",
            f"hook_budget: {self.hook_budget}",
            f"interaction_reason: {self.reason}",
            "interaction_rule: Short does not mean dead-end. Add a small information gain when hook_budget is above 0.",
            "interaction_rule: Information gain can be emotion, concrete answer, tiny tease, context connection, or one light follow-up.",
            "interaction_rule: Do not force a new topic. Do not ask a question when hook_budget is 0.",
        ]
        if self.hook_budget >= 2:
            lines.append(
                "interaction_rule: A light follow-up or tease is allowed if it fits the current relationship and message."
            )
        elif self.hook_budget == 1:
            lines.append("interaction_rule: Prefer a small reaction or context connection over a full follow-up question.")
        return lines


class InteractionPolicy:
    def plan(
        self,
        *,
        message: str,
        social_snapshot: dict[str, Any] | None,
        gate_metadata: dict[str, Any] | None,
        dialogue_state: Any | None,
        direct_address: bool,
        reply_to_bot: bool,
    ) -> InteractionPlan:
        affinity = self._affinity(social_snapshot)
        message_kind = self._message_kind(message)
        directness = self._directness(
            gate_metadata=gate_metadata,
            dialogue_state=dialogue_state,
            direct_address=direct_address,
            reply_to_bot=reply_to_bot,
        )
        hook_budget = self._hook_budget(
            affinity=affinity,
            directness=directness,
            message_kind=message_kind,
        )
        mode = self._mode(message_kind=message_kind, hook_budget=hook_budget, directness=directness)
        reason = (
            f"{directness}; {message_kind}; affinity={affinity:.2f}; "
            f"hook_budget={hook_budget}"
        )
        return InteractionPlan(
            mode=mode,
            hook_budget=hook_budget,
            affinity=affinity,
            directness=directness,
            message_kind=message_kind,
            reason=reason,
        )

    def _affinity(self, snapshot: dict[str, Any] | None) -> float:
        try:
            value = float((snapshot or {}).get("affinity", 0.5))
        except (TypeError, ValueError):
            value = 0.5
        return max(0.0, min(1.0, value))

    def _directness(
        self,
        *,
        gate_metadata: dict[str, Any] | None,
        dialogue_state: Any | None,
        direct_address: bool,
        reply_to_bot: bool,
    ) -> str:
        if reply_to_bot:
            return "reply_to_bot"
        if direct_address:
            return "direct_address"
        obligation = str(getattr(dialogue_state, "obligation", "") or "")
        if obligation in {"answer_required", "repair_required"}:
            return obligation
        attention = str((gate_metadata or {}).get("attention") or "")
        if attention in {"direct", "followup"}:
            return attention
        if attention == "ambient":
            return "ambient_candidate"
        return "ambient"

    def _message_kind(self, message: str) -> str:
        text = message.strip().casefold()
        if not text:
            return "empty"
        if self._is_question(text):
            return "question"
        if self._is_life_status(text):
            return "life_status"
        if self._is_complaint(text):
            return "complaint"
        if len(text) <= 10:
            return "short_ping"
        return "statement"

    def _hook_budget(self, *, affinity: float, directness: str, message_kind: str) -> int:
        if message_kind in {"empty"}:
            return 0
        if message_kind == "question":
            return 0
        if directness in {"reply_to_bot", "direct_address", "answer_required", "repair_required", "direct", "followup"}:
            if message_kind in {"life_status", "complaint"}:
                return 2 if affinity >= 0.75 else 1
            return 1 if affinity >= 0.35 else 0
        if message_kind in {"life_status", "complaint"} and affinity >= 0.85:
            return 1
        return 0

    def _mode(self, *, message_kind: str, hook_budget: int, directness: str) -> str:
        if message_kind == "question":
            return "answer_directly"
        if hook_budget >= 2:
            return "acknowledge_plus_hook"
        if hook_budget == 1:
            return "acknowledge_plus_emotion"
        if directness in {"reply_to_bot", "direct_address", "answer_required", "repair_required"}:
            return "bare_ack"
        return "minimal_or_no_extra"

    def _is_question(self, text: str) -> bool:
        if "?" in text or "？" in text:
            return True
        return bool(
            re.search(
                r"\b(what|which|who|where|when|why|how)\b|"
                r"(什么|哪种|哪个|哪一个|谁|哪里|几点|几天|为什么|怎么|到底)",
                text,
            )
        )

    def _is_life_status(self, text: str) -> bool:
        return bool(
            re.search(
                r"(我|i|we)?.*(下班|上班|放假|吃了|吃完|吃饭|睡了|睡不着|起床|到家|出门|"
                r"去学校|去上课|去医院|看医生|崩溃|累|困)|"
                r"\b(i|we)\s+(am|was|were|had|ate|finished|got|went|go|going)\b",
                text,
            )
        )

    def _is_complaint(self, text: str) -> bool:
        return bool(re.search(r"(烦|累死|困死|崩溃|不想|难受|头疼|糟糕|讨厌|撑不住)", text))
