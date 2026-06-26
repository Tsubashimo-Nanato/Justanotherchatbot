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
        recent_agent_replies: tuple[str, ...] = (),
        dialogue_state: Any | None = None,
    ) -> QualityReview:
        reply = reply.strip()
        if not reply:
            return QualityReview(False, False, 0.0, ("empty_reply",), ("empty_reply",))

        severe_hits = self._severe_hits(reply)
        if severe_hits:
            return QualityReview(
                send_allowed=False,
                rewrite_needed=False,
                score=0.0,
                reasons=tuple(f"blocked by {hit}" for hit in severe_hits),
                rule_hits=tuple(severe_hits),
            )

        rewrite_hits = self._rewrite_hits(
            message=message,
            reply=reply,
            interaction_plan=interaction_plan,
            recent_agent_replies=recent_agent_replies,
            dialogue_state=dialogue_state,
        )
        if rewrite_hits:
            return QualityReview(
                send_allowed=True,
                rewrite_needed=True,
                score=0.45,
                reasons=tuple(f"rewrite needed: {hit}" for hit in rewrite_hits),
                rule_hits=tuple(rewrite_hits),
            )

        return QualityReview(True, False, 0.95, ("rule_check_passed",), ())

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
        return len(reply) > 140

    def rewrite_messages(
        self,
        *,
        message: str,
        reply: str,
        reasons: tuple[str, ...],
        interaction_plan: Any | None = None,
        recent_agent_replies: tuple[str, ...] = (),
        dialogue_state: Any | None = None,
    ) -> list[dict[str, str]]:
        interaction_text = self._interaction_summary(interaction_plan)
        recent_text = "\n".join(f"- {item}" for item in recent_agent_replies if item.strip()) or "none"
        return [
            {
                "role": "system",
                "content": (
                    "Rewrite the assistant reply into one natural QQ group-chat message. "
                    "Do not mention AI, models, prompts, tools, tokens, or system state. "
                    "Do not merely repeat the user's words. Follow reply_shape from the interaction policy: "
                    "answer_with_reaction answers first and adds a small reaction; "
                    "answer_with_context_hook answers first and adds one light hook; "
                    "ack_with_light_hook acknowledges and adds a small context connection. "
                    "If the user is asking what a previous bot reply meant, explain or repair that previous reply directly. "
                    "Do not answer a clarification with another confused marker. "
                    "Output only the rewritten chat message."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"latest user message:\n{message}\n\n"
                    f"bad reply:\n{reply}\n\n"
                    f"recent assistant replies:\n{recent_text}\n\n"
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
                    "You are a strict reply quality judge for a QQ character chatbot. "
                    "Return JSON only: {\"send_allowed\": true|false, \"rewrite_needed\": true|false, "
                    "\"score\": 0.0, \"reason\": \"short reason\"}. "
                    "Penalize leaks, repeated echoes, empty dead-end replies, and answers that ignore a concrete follow-up."
                ),
            },
            {"role": "user", "content": f"user message:\n{message}\n\ncandidate reply:\n{reply}"},
        ]

    def _severe_hits(self, reply: str) -> list[str]:
        lowered = reply.casefold()
        terms = (
            "as an ai",
            "as a language model",
            "language model",
            "system prompt",
            "developer message",
            "internal config",
            "api provider",
            "xai_api_key",
            "人格文件",
            "系统提示",
            "开发者消息",
            "内部配置",
            "token",
            "prompt",
        )
        return [term for term in terms if term in lowered]

    def _rewrite_hits(
        self,
        *,
        message: str,
        reply: str,
        interaction_plan: Any | None = None,
        recent_agent_replies: tuple[str, ...] = (),
        dialogue_state: Any | None = None,
    ) -> list[str]:
        hits: list[str] = []
        if self._is_dead_end_echo(message=message, reply=reply):
            hits.append("dead_end_echo")
        if self._is_contentless_marker(reply):
            hits.append("contentless_marker")
        if self._needs_information_gain(reply=reply, interaction_plan=interaction_plan) and self._is_low_value_reply(reply):
            hits.append("dead_end_without_hook")
        if self._repeats_recent_agent_reply(reply=reply, recent_agent_replies=recent_agent_replies):
            hits.append("recent_self_repeat")
        if self._misses_followup_context(message=message, reply=reply, recent_agent_replies=recent_agent_replies, dialogue_state=dialogue_state):
            hits.append("unanswered_followup")
        return hits

    def _repeats_recent_agent_reply(self, *, reply: str, recent_agent_replies: tuple[str, ...]) -> bool:
        reply_key = self._semantic_key(reply)
        if len(reply_key) < 3:
            return False
        for recent in recent_agent_replies[-4:]:
            recent_key = self._semantic_key(recent)
            if len(recent_key) < 3:
                continue
            if reply_key == recent_key:
                return True
            if reply_key in recent_key and len(reply_key) >= 4:
                return True
            if recent_key in reply_key and len(reply_key) <= len(recent_key) + 3:
                return True
        return False

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
        text = re.sub(r"^(我|俺|咱|i|we)", "", text)
        text = re.sub(r"(啊|呀|呢|吧|哦|喔|啦|了)+$", "", text)
        return text

    def _contains_cjk(self, text: str) -> bool:
        return any("\u4e00" <= char <= "\u9fff" for char in text)

    def _needs_information_gain(self, *, reply: str, interaction_plan: Any | None) -> bool:
        message_kind = str(getattr(interaction_plan, "message_kind", ""))
        if message_kind == "short_ping":
            return False
        reply_shape = str(getattr(interaction_plan, "reply_shape", "") or "")
        if reply_shape in {"answer_with_reaction", "answer_with_context_hook", "ack_with_light_hook"}:
            return True
        try:
            hook_budget = int(getattr(interaction_plan, "hook_budget", 0))
        except (TypeError, ValueError):
            hook_budget = 0
        return hook_budget > 0 and message_kind in {"life_status", "complaint", "statement"}

    def _is_low_value_reply(self, reply: str) -> bool:
        if self._is_contentless_marker(reply):
            return True
        if self._is_empty_ack(reply):
            return True
        normalized = self._semantic_key(reply)
        if self._is_generic_short_ack_key(normalized):
            return True
        generic = {
            "嗯",
            "嗯嗯",
            "哦",
            "噢",
            "啊",
            "好",
            "行",
            "是",
            "确实",
            "可以",
            "还行",
            "不知道",
            "没想好",
            "是啊",
            "嗯是啊",
            "对啊",
            "确实啊",
        }
        if normalized in generic:
            return True
        return bool(re.fullmatch(r"(嗯+|哦+|噢+|啊+|好+|行+|是+)[？?。!！]*", reply.strip()))

    def _is_empty_ack(self, reply: str) -> bool:
        normalized = self._semantic_key(reply)
        return normalized in {"嗯", "嗯嗯", "哦", "噢", "好", "行", "是", "啊", "诶"}

    def _is_contentless_marker(self, reply: str) -> bool:
        text = reply.strip()
        if not text:
            return True
        normalized = self._semantic_key(text)
        if self._is_generic_short_ack_key(normalized):
            return True
        if not self._semantic_key(text):
            return True
        return bool(re.fullmatch(r"[\.。…\s]*(嗯|哦|噢|啊|诶)?[\.。…\s]*[？?]?[\.。…\s]*", text))

    def _is_generic_short_ack_key(self, normalized: str) -> bool:
        if len(normalized) > 4:
            return False
        generic = {
            "\u55ef",
            "\u55ef\u55ef",
            "\u54e6",
            "\u554a",
            "\u662f",
            "\u662f\u554a",
            "\u55ef\u662f\u554a",
            "\u5bf9",
            "\u5bf9\u554a",
            "\u597d",
            "\u884c",
            "\u786e\u5b9e",
            "\u786e\u5b9e\u554a",
            "\u4e0d\u77e5\u9053",
        }
        if normalized in generic:
            return True
        return bool(
            re.fullmatch(
                r"(\u55ef|\u54e6|\u554a|\u662f|\u5bf9|\u597d|\u884c){1,4}",
                normalized,
            )
        )

    def _misses_followup_context(
        self,
        *,
        message: str,
        reply: str,
        recent_agent_replies: tuple[str, ...],
        dialogue_state: Any | None,
    ) -> bool:
        if not recent_agent_replies:
            return False
        obligation = str(getattr(dialogue_state, "obligation", "") or "")
        question_like = bool(getattr(dialogue_state, "metadata", {}).get("question_or_clarification")) if dialogue_state else False
        if obligation not in {"answer_required", "repair_required"} and not question_like:
            return False

        message_key = self._semantic_key(message)
        if not self._asks_about_previous_words(message_key):
            return False
        if self._is_contentless_marker(reply):
            return True
        reply_key = self._semantic_key(reply)
        if "突然" in reply or "怎么突然" in reply:
            return True
        if "不知道" in reply_key or "不懂" in reply_key:
            return True
        return False

    def _asks_about_previous_words(self, message_key: str) -> bool:
        markers = (
            "懂啥",
            "啥意思",
            "什么意思",
            "说啥",
            "哪种",
            "哪个",
            "哪一个",
            "什么",
            "谁",
        )
        return any(marker in message_key for marker in markers)

    def _interaction_summary(self, interaction_plan: Any | None) -> str:
        if interaction_plan is None:
            return "none"
        metadata = interaction_plan.to_metadata() if hasattr(interaction_plan, "to_metadata") else {}
        return json.dumps(metadata, ensure_ascii=False, sort_keys=True)

    def _parse_json(self, raw_content: str) -> dict[str, Any] | None:
        text = raw_content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _clamp(self, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(number, 1.0))
