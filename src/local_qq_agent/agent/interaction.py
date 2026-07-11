from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


@dataclass(frozen=True)
class InteractionPlan:
    mode: str
    reply_shape: str
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
            f"reply_shape: {self.reply_shape}",
            f"hook_budget: {self.hook_budget}",
            f"interaction_reason: {self.reason}",
            "interaction_rule: Follow reply_shape before deciding length. Short is fine; dead-end is not.",
            "interaction_rule: Information gain can be a direct answer, emotion, concrete detail, tiny tease, or context connection.",
            "interaction_rule: Do not force a new topic. Avoid follow-up questions unless reply_shape explicitly allows a hook.",
        ]
        if self.reply_shape == "answer_with_context_hook":
            lines.append("interaction_rule: Answer first, then add one light context hook or low-pressure follow-up if natural.")
        elif self.reply_shape == "answer_with_reaction":
            lines.append("interaction_rule: Answer first, then add a small reaction; do not turn it into an interview.")
        elif self.reply_shape == "repair_with_context":
            lines.append(
                "interaction_rule: The user is correcting, criticizing, or giving a style/memory control instruction. "
                "Address that latest instruction first, then add one small natural recovery line. "
                "Do not keep answering the previous topic."
            )
        elif self.reply_shape == "answer_only":
            lines.append("interaction_rule: Answer the concrete question cleanly; no extra topic needed.")
        elif self.reply_shape == "ack_with_light_hook":
            lines.append(
                "interaction_rule: Acknowledge the message and add one small context connection, tease, or gentle hook."
            )
        else:
            lines.append("interaction_rule: Minimal acknowledgement is enough; do not stretch the conversation.")
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
        continuation_budget: int | None = None,
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
            continuation_budget=continuation_budget,
        )
        mode = self._mode(message_kind=message_kind, hook_budget=hook_budget, directness=directness)
        reply_shape = self._reply_shape(message_kind=message_kind, hook_budget=hook_budget)
        reason = (
            f"{directness}; {message_kind}; affinity={affinity:.2f}; "
            f"hook_budget={hook_budget}; reply_shape={reply_shape}"
        )
        return InteractionPlan(
            mode=mode,
            reply_shape=reply_shape,
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
        text = message.strip()
        if not text:
            return "empty"
        lowered = text.casefold()
        if self._is_correction_or_debug_complaint(lowered):
            return "correction"
        if self._is_question(lowered):
            return "question"
        if self._is_life_status(lowered):
            return "life_status"
        if self._is_complaint(lowered):
            return "complaint"
        if self._is_emoji_or_symbol_only(text) or len(text) <= 10:
            return "short_ping"
        return "statement"

    def _hook_budget(
        self,
        *,
        affinity: float,
        directness: str,
        message_kind: str,
        continuation_budget: int | None = None,
    ) -> int:
        if continuation_budget is not None:
            return max(0, min(3, int(continuation_budget)))
        if message_kind == "empty":
            return 0
        if message_kind == "question":
            if directness in {"reply_to_bot", "direct_address", "answer_required", "repair_required", "direct", "followup"}:
                return 2 if affinity >= 0.75 else 1
            return 1 if affinity >= 0.75 else 0
        if message_kind == "correction":
            if directness in {"reply_to_bot", "direct_address", "answer_required", "repair_required", "direct", "followup"}:
                return 2 if affinity >= 0.45 else 1
            return 1 if affinity >= 0.75 else 0
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
        if message_kind == "correction":
            return "repair_context" if hook_budget > 0 else "answer_directly"
        if hook_budget >= 2:
            return "acknowledge_plus_hook"
        if hook_budget == 1:
            return "acknowledge_plus_emotion"
        if directness in {"reply_to_bot", "direct_address", "answer_required", "repair_required"}:
            return "bare_ack"
        return "minimal_or_no_extra"

    def _reply_shape(self, *, message_kind: str, hook_budget: int) -> str:
        if message_kind == "question":
            if hook_budget >= 2:
                return "answer_with_context_hook"
            if hook_budget == 1:
                return "answer_with_reaction"
            return "answer_only"
        if message_kind == "correction":
            return "repair_with_context" if hook_budget > 0 else "answer_only"
        if hook_budget > 0:
            return "ack_with_light_hook"
        return "minimal_ack"

    def _is_question(self, text: str) -> bool:
        if self._is_plain_chinese_question(text):
            return True
        if "?" in text or "？" in text:
            return True
        english = r"\b(what|which|who|where|when|why|how|can|could|should|would|do|does|did|is|are)\b"
        chinese = (
            "什么|哪种|哪个|哪一个|谁|哪里|哪儿|几点|几号|多久|几天|"
            "为什么|怎么|咋|如何|是否|是不是|能不能|会不会|要不要|"
            "干什么|做什么|吃什么|喝什么|吗|呢"
        )
        return bool(re.search(english, text) or re.search(chinese, text))

    def _is_life_status(self, text: str) -> bool:
        if self._is_plain_chinese_life_status(text):
            return True
        if re.search(r"\b(i|we)\s+(am|was|were|had|ate|finished|got|went|go|going|will|plan)\b", text):
            return True
        return bool(
            re.search(
                r"(我|俺|咱|我们)?.*("
                r"下班|上班|放假|吃了|吃完|吃饭|晚饭|午饭|早饭|"
                r"睡了|睡不着|起床|到家|出门|去学校|去上课|去医院|看医生|"
                r"拿处方|胃不舒服|不舒服|好困|困死|累|昨晚没睡好|今天要|一会去"
                r")",
                text,
            )
        )

    def _is_complaint(self, text: str) -> bool:
        if self._is_plain_chinese_complaint(text):
            return True
        return bool(
            re.search(
                r"(烦|累死|困死|崩溃|不想|难受|头疼|糟糕|讨厌|撑不住|"
                r"慢|卡|延迟|高延迟|蠢|傻|坏掉|不会聊天|神经|抽象|怪怪的|不合理)",
                text,
            )
        )

    def _is_correction_or_debug_complaint(self, text: str) -> bool:
        if self._is_plain_chinese_correction(text):
            return True
        if re.search(
            r"(@错|at错|艾特错|引用错|回错|发错|看错|读错|漏读|没读到|没看到|"
            r"理解错|搞错|弄错|错了|不对|不是这个|不是这句|答非所问|接不上|"
            r"上下文不对|没有上下文|没上下文|重复回复|回复两次|双重回复|"
            r"为什么不发|没发出去|没有发送|发送失败|quality_blocked)",
            text,
        ):
            return True
        english = (
            "wrong",
            "misread",
            "missed",
            "duplicate reply",
            "double reply",
            "sent twice",
            "did not send",
            "failed to send",
            "wrong context",
        )
        return any(term in text for term in english)

    def _is_plain_chinese_question(self, text: str) -> bool:
        markers = (
            "\u4ec0\u4e48",
            "\u54ea",
            "\u54ea\u91cc",
            "\u8c01",
            "\u591a\u5c11",
            "\u51e0",
            "\u600e\u4e48",
            "\u4e3a\u4ec0\u4e48",
            "\u5e72\u4ec0\u4e48",
            "\u505a\u4ec0\u4e48",
            "\u5403\u4ec0\u4e48",
            "\u8bb0\u5f97\u5417",
            "\u5bf9\u5417",
            "\u597d\u5417",
            "\u884c\u5417",
        )
        if "\uFF1F" in text or any(marker in text for marker in markers):
            return True
        return bool(re.search(r"[\u4e00-\u9fff](\u5462|\u5417)$", text))

    def _is_plain_chinese_life_status(self, text: str) -> bool:
        markers = (
            "\u6ca1\u5403\u996d",
            "\u5403\u4e86",
            "\u5403\u5b8c",
            "\u65e9\u4e0a",
            "\u4e0b\u5348",
            "\u4e0a\u5348",
            "\u665a\u4e0a",
            "\u53bb\u5b66\u6821",
            "\u4e0a\u73ed",
            "\u4e0b\u73ed",
            "\u53bb\u533b\u9662",
            "\u60f3\u9003",
            "\u6709\u70b9\u70e6",
            "\u6709\u70b9\u56f0",
            "\u80c3\u4e0d\u8212\u670d",
            "\u4e0d\u8212\u670d",
        )
        return any(marker in text for marker in markers)

    def _is_plain_chinese_complaint(self, text: str) -> bool:
        markers = (
            "\u70e6",
            "\u56f0\u6b7b",
            "\u7d2f\u6b7b",
            "\u96be\u53d7",
            "\u4e0d\u60f3",
            "\u60f3\u9003",
            "\u5d29\u6e83",
            "\u5361\u4f4f",
        )
        return any(marker in text for marker in markers)

    def _is_plain_chinese_correction(self, text: str) -> bool:
        markers = (
            "\u592a\u50cf\u5ba2\u670d",
            "\u8bf4\u4eba\u8bdd",
            "\u522b\u53ea\u56de",
            "\u4e0d\u8981\u53ea\u56de",
            "\u591a\u8bf4\u51e0\u4e2a\u5b57",
            "\u4e0d\u4f1a\u804a\u5929",
            "\u7b54\u975e\u6240\u95ee",
            "\u522b\u626f",
            "\u4e0d\u8981\u626f",
            "\u4e71\u626f",
            "\u522b\u5ffd\u7136",
            "\u4e0d\u8981\u5ffd\u7136",
            "\u522b\u50cf\u673a\u5668\u4eba",
            "\u673a\u5668\u4eba\u90a3\u79cd\u8bed\u6c14",
            "\u4e0d\u8981\u5b89\u6170\u673a\u5668\u4eba",
            "\u522b\u5b89\u6170\u673a\u5668\u4eba",
            "\u522b\u5ba2\u670d",
            "\u56de\u590d\u6a21\u677f",
            "\u5199\u56de\u590d\u6a21\u677f",
            "\u50cfp1",
            "\u7b80\u77ed\u4f46\u6709\u4fe1\u606f\u91cf",
            "\u8fd9\u79cd\u98ce\u683c",
            "\u8fd8\u7b97\u6ca1\u7b28",
            "\u6ca1\u7b28",
            "\u8bb0\u4f4f\u4e09\u5929",
            "\u4e09\u5929\u5dee\u4e0d\u591a",
            "\u903b\u8f91\u4e0d\u5bf9",
            "\u6ca1\u903b\u8f91",
            "\u4e0a\u4e0b\u6587\u4e0d\u5bf9",
            "\u6ca1\u6709\u4e0a\u4e0b\u6587",
            "\u6ca1\u770b\u4e0a\u4e0b\u6587",
            "\u6ca1\u770b\u61c2",
            "\u4e0d\u5bf9",
            "\u9519\u4e86",
        )
        return any(marker in text for marker in markers)

    def _is_emoji_or_symbol_only(self, text: str) -> bool:
        visible = [char for char in text if not char.isspace()]
        if not visible:
            return False
        has_word = any(char.isalnum() or "\u4e00" <= char <= "\u9fff" for char in visible)
        return not has_word
