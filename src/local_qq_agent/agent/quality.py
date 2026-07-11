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

        severe_hits = self._severe_hits(message=message, reply=reply)
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
                    "Do not mention implementation details, hidden instructions, or system state. "
                    "Do not merely repeat the user's words. Follow reply_shape from the interaction policy: "
                    "answer_with_reaction answers first and adds a small reaction; "
                    "answer_with_context_hook answers first and adds one light hook; "
                    "ack_with_light_hook acknowledges and adds a small context connection. "
                    "repair_with_context directly addresses the user's correction or criticism before adding anything else. "
                    "If the user says the reply is too customer-service-like, too short, or asks you to speak more naturally, "
                    "demonstrate the better style in the current reply; do not promise to change next time. "
                    "If the user is asking what a previous bot reply meant, explain or repair that previous reply directly. "
                    "Do not answer a clarification with another confused marker. "
                    "Remove parenthetical stage directions and any self-invented body state, meal, work, location, or action. "
                    "When fixing a hallucinated scene, keep the useful answer and delete the invented scene; do not add a new scene. "
                    "When fixing unrelated memory attachment, keep only the part relevant to the latest message and remove unrelated remembered facts. "
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

    def _severe_hits(self, *, message: str, reply: str) -> list[str]:
        lowered = reply.casefold()
        message_lower = message.casefold()
        hard_terms = (
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
        )
        hits = [term for term in hard_terms if term in lowered]

        # These are ordinary debugging words when the user brought them up first.
        # Block only unsolicited leakage, not a natural answer to a token/prompt complaint.
        for term in ("token", "tokens"):
            if term in lowered and term not in message_lower:
                hits.append(term)
        if "prompt" in lowered and "prompt" not in message_lower:
            hits.append("prompt")
        return hits

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
        if self._has_harness_phrase(reply):
            hits.append("harness_phrase")
        if self._needs_information_gain(reply=reply, interaction_plan=interaction_plan) and self._is_low_value_reply(reply):
            hits.append("dead_end_without_hook")
        if self._misses_correction_repair(message=message, reply=reply, interaction_plan=interaction_plan):
            hits.append("unrepaired_correction")
        if self._misses_plain_style_repair(message=message, reply=reply, interaction_plan=interaction_plan):
            hits.append("unrepaired_correction")
        if self._repeats_recent_agent_reply(reply=reply, recent_agent_replies=recent_agent_replies):
            hits.append("recent_self_repeat")
        if self._has_parenthetical_stage_direction(message=message, reply=reply):
            hits.append("stage_direction")
        if self._has_offscreen_self_claim(message=message, reply=reply):
            hits.append("offscreen_self_claim")
        if self._has_unprovided_scene_detail(message=message, reply=reply):
            hits.append("unprovided_scene_detail")
        if str(getattr(interaction_plan, "message_kind", "")) != "correction" and self._misses_followup_context(
            message=message,
            reply=reply,
            recent_agent_replies=recent_agent_replies,
            dialogue_state=dialogue_state,
        ):
            hits.append("unanswered_followup")
        if self._misses_retention_uncertainty(message=message, reply=reply):
            hits.append("overconfident_retention")
        if self._misses_meta_feedback(message=message, reply=reply):
            hits.append("unanswered_meta_feedback")
        if self._has_unrelated_memory_attachment(message=message, reply=reply):
            hits.append("unrelated_memory_attachment")
        return hits

    def strip_parenthetical_asides(self, reply: str) -> str:
        cleaned = re.sub(r"[\(\uFF08][^\)\uFF09]{1,120}[\)\uFF09]", "", reply)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def strip_unprovided_scene_details(self, reply: str) -> str:
        chunks = re.split(r"(?<=[\u3002\uff01\uff1f!?])\s+|\n+", reply)
        kept: list[str] = []
        for chunk in chunks:
            text = chunk.strip()
            if not text:
                continue
            if self._contains_unprovided_scene_term(text):
                continue
            kept.append(text)
        return "\n".join(kept).strip()

    def _contains_unprovided_scene_term(self, text: str) -> bool:
        lowered = text.casefold()
        terms = (
            "homework",
            "screen",
            "drawer",
            "window",
            "\u4f5c\u4e1a",
            "\u4e66\u5305",
            "\u4f1e",
            "\u5c4f\u5e55",
            "\u62bd\u5c49",
            "\u7a97",
            "\u697c\u4e0b",
            "\u4e0b\u96e8",
            "\u542c\u89c1",
            "\u542c\u8bf4",
            "\u5fc3\u8df3",
            "\u4fbf\u5229\u5e97",
            "\u6628\u5929",
            "\u5976\u8336",
            "\u4f1e",
            "\u540c\u5b66",
            "\u649e\u89c1",
            "\u6e9c\u51fa\u53bb",
            "\u8bfe\u684c",
            "\u952e\u76d8",
            "\u5df7\u53e3",
            "\u5c0f\u5e97",
            "\u624b\u64c0\u9762",
            "\u8471\u82b1",
            "\u6628\u5929",
        )
        return any(term in lowered for term in terms)

    def _has_parenthetical_stage_direction(self, *, message: str, reply: str) -> bool:
        if "(" not in reply and ")" not in reply and "\uFF08" not in reply and "\uFF09" not in reply:
            return False
        if "(" in message or "\uFF08" in message:
            return False
        return bool(re.search(r"[\(\uFF08][^\)\uFF09]{1,80}[\)\uFF09]", reply))

    def _has_offscreen_self_claim(self, *, message: str, reply: str) -> bool:
        lowered_message = message.casefold()
        lowered_reply = reply.casefold()
        if not re.search(r"\b(i|me|my|myself)\b|\u6211", lowered_reply):
            return False

        allowed_if_user_asked_about_bot = self._asks_about_bot_state(lowered_message)
        if allowed_if_user_asked_about_bot:
            return False

        if re.search(
            r"\u6211.{0,8}(\u521a|\u4e5f|\u8fd9\u8fb9|\u8fd9\u91cc|\u81ea\u5df1)?.{0,8}"
            r"(\u5403|\u559d|\u7761|\u4e0a\u73ed|\u5de5\u4f5c|\u716e|\u6ce1|\u8d70|\u53bb)",
            lowered_reply,
        ):
            return True
        if re.search(r"\b(i|me|myself)\b.{0,24}\b(eat|ate|drink|sleep|slept|work|go|going)\b", lowered_reply):
            return True

        offscreen_terms = (
            "eat",
            "ate",
            "sleep",
            "slept",
            "homework",
            "work",
            "office",
            "weather",
            "wind",
            "\u5403",
            "\u5543",
            "\u996d",
            "\u996d\u5c40",
            "\u7761",
            "\u56f0",
            "\u4f5c\u4e1a",
            "\u4e0a\u73ed",
            "\u5de5\u4f5c",
            "\u5929\u6c14",
            "\u98ce",
            "\u5fc3\u8df3",
            "\u5f55",
            "\u5c4f\u5e55",
            "\u62bd\u5c49",
            "\u6ce1\u9762",
            "\u62c9\u9762",
            "\u4e4c\u51ac",
        )
        if not any(term in lowered_reply and term not in lowered_message for term in offscreen_terms):
            return False
        return True

    def _has_unprovided_scene_detail(self, *, message: str, reply: str) -> bool:
        lowered_message = message.casefold()
        lowered_reply = reply.casefold()
        scene_terms = (
            "homework",
            "heartbeat",
            "screen",
            "drawer",
            "convenience store",
            "old book",
            "cover",
            "dry noodle",
            "\u4f5c\u4e1a",
            "\u5fc3\u8df3",
            "\u4f1e",
            "\u5c4f\u5e55",
            "\u7a97\u5916",
            "\u542c\u89c1",
            "\u542c\u5230",
            "\u98d8\u6765",
            "\u521a\u4ece",
            "\u9694\u58c1",
            "\u697c",
            "\u697c\u4e0b",
            "\u98ce\u91cc",
            "\u4e0b\u96e8",
            "\u542c\u8bf4",
            "\u4fbf\u5229\u5e97",
            "\u62bd\u5c49",
            "\u996d\u5c40",
            "\u65e7\u4e66",
            "\u5c01\u9762",
            "\u7ffb\u5b8c",
            "\u6478\u70c2",
            "\u521a\u628a",
            "\u5976\u8336",
            "\u540c\u5b66",
            "\u649e\u89c1",
            "\u6e9c\u51fa\u53bb",
            "\u8bfe\u684c",
            "\u952e\u76d8",
            "\u5df7\u53e3",
            "\u5c0f\u5e97",
            "\u624b\u64c0\u9762",
            "\u8471\u82b1",
            "\u5e72\u5403",
            "\u8fb9\u5403",
            "\u6162\u70b9",
            "\u9012\u7eb8\u5dfe",
            "\u9003\u5b66\u5927\u4f5c\u6218",
            "\u70ed\u9505",
            "\u714e\u86cb",
            "\u592a\u9633",
            "\u51b0\u68cd",
            "\u6ef4\u6c34",
            "\u63a8\u4e86\u63a8",
            "\u7897",
            "\u6628\u5929",
            "\u53e3\u888b",
            "\u94b1\u5305",
            "\u997c\u5e72",
            "\u7fd8\u4e86",
            "\u7fd8\u8bfe",
            "\u6559\u5ba4",
            "\u4e00\u7b77\u5b50",
            "\u5939\u8d77\u6765",
            "\u4f1a\u6296",
            "\u5fc3\u7406\u63f4\u52a9",
            "\u670d\u52a1",
            "\u8bf4\u660e\u4e66",
        )
        if any(marker in lowered_message for marker in ("\u5929\u6c14", "\u96e8", "\u4e0b\u96e8", "\u6c14\u6e29")):
            scene_terms = tuple(
                term
                for term in scene_terms
                if term not in {"\u96e8", "\u4e0b\u96e8", "\u4f1e", "\u542c\u8bf4"}
            )
        if re.search(r"\u300a[^\\u300b]{1,24}\u300b", reply) and not re.search(r"\u300a[^\\u300b]{1,24}\u300b", message):
            return True
        return any(term in lowered_reply and term not in lowered_message for term in scene_terms)

    def _misses_retention_uncertainty(self, *, message: str, reply: str) -> bool:
        message_key = self._semantic_key(message)
        reply_key = self._semantic_key(reply)
        if "\u4e09\u5929\u540e" not in message_key:
            return False
        uncertain = ("\u4e0d\u4e00\u5b9a", "\u5fd8", "\u518d\u8bf4", "\u5230\u65f6\u5019")
        if any(marker in reply for marker in uncertain):
            return False
        overconfident = ("\u8bb0\u5f97", "\u8bb0\u4f4f", "\u8bb0\u7262", "\u8fd8\u8bb0", "\u4fdd\u51c6", "\u8fd8\u662f", "\u6211\u5c31\u8bf4")
        return any(marker in reply_key for marker in overconfident)

    def _misses_meta_feedback(self, *, message: str, reply: str) -> bool:
        message_key = self._semantic_key(message)
        reply_key = self._semantic_key(reply)
        if "\u65e7\u4e66\u5c01\u9762" in message_key:
            acknowledged = any(marker in reply_key for marker in ("\u4e0d\u8bb2", "\u4e0d\u626f", "\u4e0d\u63d0", "\u4e71\u626f"))
            return not acknowledged
        if "\u8fd8\u7b97\u6ca1\u7b28" in message_key or "\u6ca1\u7b28" in message_key:
            acknowledged = any(marker in reply_key for marker in ("\u6ca1\u7b28", "\u8fd8\u7b97", "\u8fd8\u884c"))
            return not acknowledged
        if "\u8fd9\u79cd\u98ce\u683c" in message_key or "\u50cfp1" in message_key:
            return len(reply_key) <= 3
        return False

    def _has_harness_phrase(self, reply: str) -> bool:
        phrases = (
            "\u6211\u6536\u4e00\u4e0b",
            "\u50cf\u5728\u8bfb\u8868",
            "\u6309\u4f60\u521a\u624d",
            "\u4e0d\u8865\u4e0d\u5b58\u5728\u7684\u7ec6\u8282",
            "\u4e0d\u786c\u63a5",
            "\u4e0d\u5f80\u5916\u7f16",
            "\u4f60\u8fd9\u53e5\u8bf4\u5230\u54ea",
            "\u6211\u5c31\u63a5\u5230\u54ea",
        )
        return any(phrase in reply for phrase in phrases)

    def _has_unrelated_memory_attachment(self, *, message: str, reply: str) -> bool:
        """Catch replies that staple unrelated remembered facts onto a current turn.

        This is intentionally about memory categories, not topic semantics. The
        model may use memory when the latest message asks for that category, but
        it should not append color-number tests, schedules, allergy facts, or
        preference facts as filler to an unrelated answer.
        """
        message_key = self._semantic_key(message)
        reply_key = self._semantic_key(reply)
        categories = (
            (
                "color_code",
                ("114514", "1919810", "\u84dd\u8272", "\u7ea2\u8272", "\u6697\u53f7"),
                ("114514", "1919810", "\u84dd\u8272", "\u7ea2\u8272", "\u591a\u5c11", "\u4ee3\u8868", "\u6697\u53f7", "\u989c\u8272"),
            ),
            (
                "hospital_plan",
                ("\u533b\u9662", "\u590d\u67e5", "\u8bca\u6240"),
                ("\u533b\u9662", "\u590d\u67e5", "\u8bca\u6240", "\u53bb\u54ea", "\u5b89\u6392", "\u660e\u5929", "\u4e0b\u5348"),
            ),
            (
                "allergy",
                ("\u8d1d\u7c7b", "\u8fc7\u654f"),
                ("\u8d1d\u7c7b", "\u8fc7\u654f", "\u5fcc\u53e3", "\u907f\u5f00", "\u80fd\u4e0d\u80fd\u5403"),
            ),
            (
                "food_preference",
                ("\u66f4\u504f\u8fa3", "\u4e0d\u559c\u6b22\u751c", "\u751c\u98df", "\u8fa3\u7684", "\u751c\u7684", "\u8fa3\u548c\u751c", "\u8fa3\u751c"),
                ("\u5403\u4ec0\u4e48", "\u66f4\u504f", "\u8fa3", "\u751c", "\u63a8", "\u559c\u6b22", "\u504f\u597d"),
            ),
        )

        for _name, reply_markers, allowed_message_markers in categories:
            if not any(marker in reply_key for marker in reply_markers):
                continue
            if self._memory_query_allows_category(
                message_key=message_key,
                category=_name,
                allowed_markers=allowed_message_markers,
            ):
                continue
            return True
        return False

    def _memory_query_allows_category(
        self,
        *,
        message_key: str,
        category: str,
        allowed_markers: tuple[str, ...],
    ) -> bool:
        if any(marker in message_key for marker in allowed_markers):
            return True
        if any(marker in message_key for marker in ("\u603b\u7ed3", "\u91cd\u70b9", "\u4f60\u8bb0\u4f4f", "\u8bb0\u4f4f\u7684")):
            return True
        if category == "hospital_plan":
            return any(marker in message_key for marker in ("\u4e2d\u671f", "\u5b89\u6392", "\u53bb\u54ea"))
        if category == "food_preference":
            return any(marker in message_key for marker in ("\u957f\u671f", "\u504f\u597d", "\u5403\u4ec0\u4e48"))
        if category == "allergy":
            return any(marker in message_key for marker in ("\u8fc7\u654f", "\u5fcc\u53e3", "\u80fd\u4e0d\u80fd\u5403"))
        return False

    def _asks_about_bot_state(self, lowered_message: str) -> bool:
        if re.search(r"\b(what are you doing|did you eat|are you awake|are you tired|yourself)\b", lowered_message):
            return True
        markers = (
            "\u4f60\u5403",
            "\u4f60\u559d",
            "\u4f60\u7761",
            "\u4f60\u56f0",
            "\u4f60\u5728\u5e72\u561b",
            "\u4f60\u5728\u505a\u4ec0\u4e48",
            "\u4f60\u81ea\u5df1",
            "\u4f60\u4eca\u5929",
            "\u4f60\u521a",
        )
        return any(marker in lowered_message for marker in markers)

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
        text = re.sub(r"^(我|你|咱|俺|i|we)", "", text)
        text = re.sub(r"(啊|呀|呢|嘛|吧|哦|喔|嗯)+$", "", text)
        return text

    def _contains_cjk(self, text: str) -> bool:
        return any("\u4e00" <= char <= "\u9fff" for char in text)

    def _needs_information_gain(self, *, reply: str, interaction_plan: Any | None) -> bool:
        message_kind = str(getattr(interaction_plan, "message_kind", ""))
        if message_kind == "short_ping":
            return False
        reply_shape = str(getattr(interaction_plan, "reply_shape", "") or "")
        if reply_shape in {"answer_with_reaction", "answer_with_context_hook", "ack_with_light_hook", "repair_with_context"}:
            return True
        try:
            hook_budget = int(getattr(interaction_plan, "hook_budget", 0))
        except (TypeError, ValueError):
            hook_budget = 0
        return hook_budget > 0 and message_kind in {"life_status", "complaint", "correction", "statement"}

    def _is_low_value_reply(self, reply: str) -> bool:
        if self._is_contentless_marker(reply):
            return True
        if self._is_empty_ack(reply):
            return True
        normalized = self._semantic_key(reply)
        if normalized in {
            "\u55ef",
            "\u55ef\u55ef",
            "\u597d",
            "\u597d\u7684",
            "\u884c",
            "\u77e5\u9053\u4e86",
            "\u55ef\u77e5\u9053\u4e86",
            "\u77e5\u9053\u4e86\u4e0b\u6b21",
            "\u662f\u554a",
            "\u5bf9\u554a",
            "\u786e\u5b9e",
            "\u786e\u5b9e\u554a",
            "\u4e0b\u73ed\u4e86\u554a",
        }:
            return True
        if self._is_generic_short_ack_key(normalized):
            return True
        generic = {
            "确实",
            "可以",
            "还行",
            "不知道",
            "没想好",
            "是啊",
            "嗯是啊",
            "对啊",
            "确实啊",
            "下班了",
            "下班了啊",
        }
        if normalized in generic:
            return True
        return bool(re.fullmatch(r"(嗯|哦|噢|啊|好|行|是|对)[。！？\s]*", reply.strip()))

    def _misses_correction_repair(self, *, message: str, reply: str, interaction_plan: Any | None) -> bool:
        if str(getattr(interaction_plan, "message_kind", "")) != "correction":
            return False
        reply_key = self._semantic_key(reply)
        if self._is_contentless_marker(reply):
            return True
        dodges = (
            "还活着",
            "装傻",
            "怎么突然",
            "什么情况",
            "满分",
            "懂了",
        )
        if any(term in reply for term in dodges):
            return True
        repair_markers = (
            "错",
            "不对",
            "刚才",
            "我看",
            "看错",
            "读错",
            "回错",
            "发错",
            "引用",
            "艾特",
            "@",
            "接错",
            "漏",
            "重新",
            "这句",
            "那句",
        )
        if any(marker in reply for marker in repair_markers):
            return False
        message_key = self._semantic_key(message)
        return len(message_key) >= 3 and message_key not in reply_key

    def _misses_plain_style_repair(self, *, message: str, reply: str, interaction_plan: Any | None) -> bool:
        if str(getattr(interaction_plan, "message_kind", "")) != "correction":
            return False
        if not any(
            marker in message
            for marker in (
                "\u592a\u50cf\u5ba2\u670d",
                "\u8bf4\u4eba\u8bdd",
                "\u522b\u53ea\u56de",
                "\u4e0d\u8981\u53ea\u56de",
                "\u63a5\u4e00\u53e5\u81ea\u7136\u7684",
                "\u522b\u50cf\u673a\u5668\u4eba",
                "\u673a\u5668\u4eba\u90a3\u79cd\u8bed\u6c14",
                "\u4e0d\u8981\u5b89\u6170\u673a\u5668\u4eba",
                "\u522b\u5b89\u6170\u673a\u5668\u4eba",
                "\u522b\u5ba2\u670d",
                "\u56de\u590d\u6a21\u677f",
                "\u5199\u56de\u590d\u6a21\u677f",
                "\u50cfp1",
                "\u7b80\u77ed\u4f46\u6709\u4fe1\u606f\u91cf",
            )
        ):
            return False
        normalized = self._semantic_key(reply)
        if normalized in {
            "\u77e5\u9053\u4e86",
            "\u55ef\u77e5\u9053\u4e86",
            "\u77e5\u9053\u4e86\u4e0b\u6b21",
            "\u4e0b\u6b21\u4e0d\u53ea\u56de\u4e00\u53e5",
        }:
            return True
        if any(marker in reply for marker in ("\u4e0b\u6b21", "\u4e0b\u56de", "\u4ee5\u540e")):
            return True
        return False

    def _is_empty_ack(self, reply: str) -> bool:
        normalized = self._semantic_key(reply)
        if normalized in {
            "\u55ef",
            "\u55ef\u55ef",
            "\u54e6",
            "\u5662",
            "\u597d",
            "\u884c",
            "\u662f",
            "\u554a",
            "\u8bf4",
            "\u77e5\u9053\u4e86",
            "\u55ef\u77e5\u9053\u4e86",
        }:
            return True
        return normalized in {"嗯", "嗯嗯", "哦", "噢", "好", "行", "是", "啊", "说"}

    def _is_contentless_marker(self, reply: str) -> bool:
        text = reply.strip()
        if not text:
            return True
        normalized = self._semantic_key(text)
        if normalized in {
            "\u55ef",
            "\u55ef\u55ef",
            "\u54e6",
            "\u5662",
            "\u554a",
            "\u8bf6",
            "\u597d",
            "\u884c",
            "\u8bf4",
        }:
            return True
        if self._is_generic_short_ack_key(normalized):
            return True
        if not normalized:
            return True
        return bool(re.fullmatch(r"[\.\s]*(嗯|哦|噢|啊|说)?[\.\s]*[？?]?[\.\s]*", text))

    def _is_generic_short_ack_key(self, normalized: str) -> bool:
        if len(normalized) > 4:
            return False
        if normalized in {
            "\u55ef",
            "\u55ef\u55ef",
            "\u54e6",
            "\u5662",
            "\u554a",
            "\u597d",
            "\u884c",
            "\u662f",
            "\u5bf9",
            "\u8bf4",
            "\u786e\u5b9e",
        }:
            return True
        generic = {
            "嗯",
            "嗯嗯",
            "哦",
            "啊",
            "是",
            "是啊",
            "嗯是啊",
            "对",
            "对啊",
            "好",
            "行",
            "确实",
            "确实啊",
            "不知道",
        }
        if normalized in generic:
            return True
        return bool(re.fullmatch(r"(嗯|哦|啊|是|对|好|行){1,4}", normalized))

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
