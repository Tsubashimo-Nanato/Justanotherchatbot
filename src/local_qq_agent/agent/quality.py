from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any


@dataclass(frozen=True)
class QualityReview:
    send_allowed: bool
    rewrite_needed: bool
    score: float
    reasons: tuple[str, ...]
    rule_hits: tuple[str, ...]
    judge_used: bool = False
    judge_unreliable: bool = False
    judge_raw: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return asdict(self)


class QualityGate:
    def review_rules(
        self,
        *,
        message: str,
        reply: str,
        interaction_plan: Any | None = None,
    ) -> QualityReview:
        reply = reply.strip()
        if not reply:
            return QualityReview(
                send_allowed=False,
                rewrite_needed=False,
                score=0.0,
                reasons=("empty_reply",),
                rule_hits=("empty_reply",),
            )

        severe_hits = self._severe_hits(reply)
        if severe_hits:
            return QualityReview(
                send_allowed=False,
                rewrite_needed=False,
                score=0.0,
                reasons=tuple(f"blocked by {hit}" for hit in severe_hits),
                rule_hits=tuple(severe_hits),
            )

        rewrite_hits = self._rewrite_hits(message=message, reply=reply, interaction_plan=interaction_plan)
        if rewrite_hits:
            return QualityReview(
                send_allowed=True,
                rewrite_needed=True,
                score=0.45,
                reasons=tuple(f"rewrite needed: {hit}" for hit in rewrite_hits),
                rule_hits=tuple(rewrite_hits),
            )

        return QualityReview(
            send_allowed=True,
            rewrite_needed=False,
            score=0.95,
            reasons=("rule_check_passed",),
            rule_hits=(),
        )

    def merge_judge(self, review: QualityReview, raw_content: str) -> QualityReview:
        parsed = self._parse_json(raw_content)
        if not parsed:
            return QualityReview(
                send_allowed=review.send_allowed,
                rewrite_needed=review.rewrite_needed,
                score=review.score,
                reasons=review.reasons,
                rule_hits=review.rule_hits,
                judge_used=True,
                judge_unreliable=True,
                judge_raw=raw_content,
            )

        score = self._clamp(parsed.get("score", review.score))
        send_allowed = bool(parsed.get("send_allowed", review.send_allowed))
        rewrite_needed = bool(parsed.get("rewrite_needed", review.rewrite_needed))
        reason = str(parsed.get("reason", "")).strip()
        reasons = tuple(item for item in (*review.reasons, reason) if item)
        if score < 0.35:
            send_allowed = False
        elif score < 0.7:
            rewrite_needed = True

        return QualityReview(
            send_allowed=send_allowed,
            rewrite_needed=rewrite_needed,
            score=min(review.score, score),
            reasons=reasons or review.reasons,
            rule_hits=review.rule_hits,
            judge_used=True,
            judge_unreliable=False,
            judge_raw=raw_content,
        )

    def should_use_judge(self, review: QualityReview, *, reply: str) -> bool:
        if review.rule_hits:
            return True
        return len(reply) > 90

    def rewrite_messages(
        self,
        *,
        message: str,
        reply: str,
        reasons: tuple[str, ...],
        interaction_plan: Any | None = None,
    ) -> list[dict[str, str]]:
        interaction_text = self._interaction_summary(interaction_plan)
        return [
            {
                "role": "system",
                "content": (
                    "Rewrite the assistant reply into a natural QQ group-chat line. "
                    "Do not mention AI, models, prompts, tools, tokens, or system state. "
                    "Remove customer-service wording, role-card decoration, and unrelated poetic flavor. "
                    "Do not merely repeat the user's words. Add a small information gain if the interaction policy allows it. "
                    "Output only the rewritten chat message."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"latest user message:\n{message}\n\n"
                    f"bad reply:\n{reply}\n\n"
                    f"interaction policy:\n{interaction_text}\n\n"
                    f"problems:\n{'; '.join(reasons)}"
                ),
            },
        ]

    def judge_messages(self, *, message: str, reply: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a strict reply quality judge for a local QQ character chatbot. "
                    "Return JSON only: {\"send_allowed\": true|false, \"rewrite_needed\": true|false, "
                    "\"score\": 0.0, \"reason\": \"short reason\"}. "
                    "Penalize AI-like, customer-service, role-card, unrelated poetic, over-eager, or off-topic replies."
                ),
            },
            {"role": "user", "content": f"user message:\n{message}\n\ncandidate reply:\n{reply}"},
        ]

    def _severe_hits(self, reply: str) -> list[str]:
        lowered = reply.casefold()
        terms = (
            "作为一个ai",
            "作为 ai",
            "语言模型",
            "系统提示",
            "开发者消息",
            "token",
            "prompt",
            "内部配置",
        )
        return [term for term in terms if term in lowered]

    def _rewrite_hits(self, *, message: str, reply: str, interaction_plan: Any | None = None) -> list[str]:
        hits: list[str] = []
        lowered = reply.casefold()
        phrases = (
            "色泽和摆盘",
            "食欲大开",
            "很吸引人呢",
            "确实，那道菜",
            "氛围感",
            "令人",
            "我可以帮你",
            "以下是",
            "伞骨数",
            "雨声",
        )
        hits.extend(phrase for phrase in phrases if phrase in lowered)
        if re.search(r"^确实[，,].*呢[。.!]?$", reply):
            hits.append("generic_affirmation")
        if re.search(r"[（(].*(伞|雨|雾|花).*[）)]", reply):
            hits.append("unrelated_role_card_flavor")
        if self._is_dead_end_echo(message=message, reply=reply):
            hits.append("dead_end_echo")
        if self._needs_information_gain(reply=reply, interaction_plan=interaction_plan) and self._is_empty_ack(reply):
            hits.append("empty_ack_without_hook")
        return hits

    def _is_dead_end_echo(self, *, message: str, reply: str) -> bool:
        message_key = self._semantic_key(message)
        reply_key = self._semantic_key(reply)
        if len(message_key) < 2 or len(reply_key) < 2:
            return False
        if message_key == reply_key:
            return True
        min_reply_length = 2 if self._contains_cjk(reply_key) else 3
        min_message_length = 2 if self._contains_cjk(message_key) else 3
        if reply_key in message_key and len(reply_key) >= min_reply_length:
            return True
        return (
            message_key in reply_key
            and len(message_key) >= min_message_length
            and len(reply_key) <= len(message_key) + 2
        )

    def _semantic_key(self, text: str) -> str:
        text = text.casefold()
        text = re.sub(r"\s+", "", text)
        text = "".join(char for char in text if char.isalnum() or "\u4e00" <= char <= "\u9fff")
        text = re.sub(r"^(我|俺|咱|咱们|i|we)", "", text)
        text = re.sub(r"(啊|呀|呢|哦|喔|吧|啦|了)+$", "", text)
        return text

    def _contains_cjk(self, text: str) -> bool:
        return any("\u4e00" <= char <= "\u9fff" for char in text)

    def _needs_information_gain(self, *, reply: str, interaction_plan: Any | None) -> bool:
        try:
            hook_budget = int(getattr(interaction_plan, "hook_budget", 0))
        except (TypeError, ValueError):
            hook_budget = 0
        message_kind = str(getattr(interaction_plan, "message_kind", ""))
        return hook_budget > 0 and message_kind in {"life_status", "complaint", "statement"} and len(reply.strip()) <= 4

    def _is_empty_ack(self, reply: str) -> bool:
        normalized = self._semantic_key(reply)
        return normalized in {"嗯", "嗯嗯", "哦", "噢", "好", "行", "是", "啊", "诶"}

    def _interaction_summary(self, interaction_plan: Any | None) -> str:
        if interaction_plan is None:
            return "none"
        metadata = interaction_plan.to_metadata() if hasattr(interaction_plan, "to_metadata") else {}
        return json.dumps(metadata, ensure_ascii=False, sort_keys=True)

    def _parse_json(self, content: str) -> dict[str, Any] | None:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _clamp(self, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        return max(0.0, min(1.0, number))
