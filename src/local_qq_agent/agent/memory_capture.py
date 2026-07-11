from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


@dataclass(frozen=True)
class MemoryCapture:
    kind: str
    summary: str
    confidence: float
    scope: str
    reason: str
    ttl_seconds: int | None = None

    def to_metadata(self) -> dict[str, Any]:
        return asdict(self)


class MemoryCapturePolicy:
    SHORT_TERM_TTL_SECONDS = 3 * 24 * 60 * 60

    def capture(self, message: str) -> list[MemoryCapture]:
        text = self._normalize(message)
        if not text:
            return []

        retention = self._retention_memory(text)
        if retention:
            return retention

        explicit = self._explicit_memory(text)
        if explicit:
            return explicit

        captures: list[MemoryCapture] = []
        captures.extend(self._mapping_memory(text))
        captures.extend(self._preference_memory(text))
        if self._looks_like_question(text) or self._is_behavior_meta_instruction(text):
            return self._dedupe(captures)
        captures.extend(self._plan_memory(text))
        captures.extend(self._meal_or_status_memory(text))
        return self._dedupe(captures)

    def _explicit_memory(self, text: str) -> list[MemoryCapture]:
        markers = ("记住", "记一下", "remember")
        for marker in markers:
            index = text.casefold().find(marker.casefold())
            if index < 0:
                continue
            summary = self._clean_fragment(text[index + len(marker) :])
            if summary and self._looks_like_question(summary):
                return []
            if summary:
                mappings = self._mapping_memory(summary)
                if mappings and marker != "remember":
                    return mappings
                return [
                    MemoryCapture(
                        kind="fact",
                        summary=summary,
                        confidence=0.75,
                        scope="long_term",
                        reason="explicit_memory_request",
                    )
                ]
        return []

    def _mapping_memory(self, text: str) -> list[MemoryCapture]:
        captures: list[MemoryCapture] = []
        pattern = re.compile(
            r"(?P<key>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})\s*"
            r"(?:represents|means|is|=|:|：|代表|是)\s*"
            r"(?P<value>[0-9][0-9A-Za-z_\-\s,，]*)",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            key = self._clean_fragment(match.group("key"))
            value = self._clean_fragment(re.sub(r"\s+", " ", match.group("value")))
            if not key or not value:
                continue
            captures.append(
                MemoryCapture(
                    kind="fact",
                    summary=f"{key} represents {value}",
                    confidence=0.7,
                    scope="long_term",
                    reason="symbol_mapping",
                )
            )
        return captures

    def _preference_memory(self, text: str) -> list[MemoryCapture]:
        patterns = (
            (
                r"\b(?:i|we)\s+(?:really\s+|very\s+much\s+)?"
                r"(?P<verb>love|like|enjoy|prefer|hate|dislike)\s+"
                r"(?P<object>[^.!?\n]{2,120})",
                "en",
            ),
            (
                r"\bmy\s+favorite\s+(?:food|drink|thing|place|game|song|movie|anime)?\s*"
                r"(?:is|are)\s+(?P<object>[^.!?\n]{2,120})",
                "favorite",
            ),
            (
                r"(?:我|咱|我们)?(?:真的|很|特别|超)?(?P<verb>喜欢|爱吃|爱|讨厌|不喜欢)"
                r"(?P<object>[^。！？\n]{1,80})",
                "zh",
            ),
            (
                r"(?:我|咱|我们)?最喜欢(?:吃|喝|玩|看)?(?P<object>[^。！？\n]{1,80})",
                "favorite_zh",
            ),
        )
        for pattern, language in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            obj = self._clean_fragment(match.group("object"))
            if not obj:
                continue
            verb = str(match.groupdict().get("verb") or "favorite").casefold()
            polarity = "dislikes" if verb in {"hate", "dislike", "讨厌", "不喜欢"} else "likes"
            if language in {"favorite", "favorite_zh"}:
                polarity = "favorite"
            return [
                MemoryCapture(
                    kind="preference",
                    summary=f"{polarity}: {obj}",
                    confidence=0.75,
                    scope="long_term",
                    reason="user_preference",
                )
            ]
        return []

    def _retention_memory(self, text: str) -> list[MemoryCapture]:
        lowered = text.casefold()
        if not ("记住" in lowered and "三天" in lowered and "上下文" in lowered):
            return []
        return [
            MemoryCapture(
                kind="working_context",
                summary="current context retention requested for about 3 days",
                confidence=0.7,
                scope="short_term",
                reason="context_retention_instruction",
                ttl_seconds=self.SHORT_TERM_TTL_SECONDS,
            )
        ]

    def _plan_memory(self, text: str) -> list[MemoryCapture]:
        if self._looks_like_question(text):
            return []

        patterns = (
            r"\b(?:i|we)\s+(?:am\s+|are\s+|'m\s+|'re\s+)?(?:going|heading)\s+to\s+(?P<activity>[^.!?\n]{2,140})",
            r"\b(?:i|we)\s+(?:will|plan\s+to|have\s+to|need\s+to|am\s+going\s+to|are\s+going\s+to)\s+(?P<activity>[^.!?\n]{2,140})",
            r"\b(?:i|we)\s+have\s+(?:a|an)\s+(?P<activity>[^.!?\n]{2,100}?(?:appointment|doctor|doctors|dentist|class|exam))\b",
            r"(?:我|咱|我们)?(?P<time>今天|明天|后天|今晚|下午|上午|晚上|周末|下周|这周|[0-9]{1,2}月[0-9]{1,2}日)?"
            r"(?:还要|要|打算|准备|可能会|会|得|需要)(?P<activity>去[^，,。！？\n]{1,60}|到[^，,。！？\n]{1,60}|[^，,。！？\n]{1,60})",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            activity = self._clean_fragment(match.group("activity"))
            if not activity:
                continue
            if self._looks_like_status_fragment(activity):
                continue
            scope = "episodic" if self._has_time_marker(text) else "working"
            confidence = 0.72 if scope == "episodic" else 0.58
            return [
                MemoryCapture(
                    kind="plan" if scope == "episodic" else "working_context",
                    summary=f"plans or current activity: {activity}",
                    confidence=confidence,
                    scope=scope,
                    reason="schedule_or_current_activity",
                    ttl_seconds=self.SHORT_TERM_TTL_SECONDS,
                )
            ]
        return []

    def _looks_like_question(self, text: str) -> bool:
        if "?" in text or "\uFF1F" in text or "\u0408\u0457" in text:
            return True
        question_markers = (
            "\u4ec0\u4e48",
            "\u591a\u5c11",
            "\u54ea",
            "\u54ea\u91cc",
            "\u53bb\u54ea",
            "\u8c01",
            "\u51e0",
            "\u600e\u4e48",
            "\u4e3a\u4ec0\u4e48",
            "\u662f\u5426",
            "\u662f\u4e0d\u662f",
            "\u80fd\u4e0d\u80fd",
            "\u4f1a\u4e0d\u4f1a",
            "\u8981\u4e0d\u8981",
            "\u8bb0\u5f97",
            "\u603b\u7ed3",
            "\u521a\u624d\u8bf4",
            "\u521a\u521a\u8bf4",
            "\u63a5\u4e00\u53e5",
            "\u50cf\u4eba\u8bf4\u8bdd",
            "\u4e0d\u8981\u53ea\u56de",
            "\u56de\u4e00\u4e2a\u5b57",
            "what",
            "which",
            "where",
            "when",
            "why",
            "how",
            "remember",
            "summarize",
        )
        lowered = text.casefold()
        return any(marker in lowered for marker in question_markers)

    def _looks_like_status_fragment(self, text: str) -> bool:
        markers = (
            "\u6709\u70b9\u70e6",
            "\u5f88\u70e6",
            "\u6709\u70b9\u56f0",
            "\u5f88\u56f0",
            "\u56f0\u6b7b",
            "\u80c3\u7a7a",
            "\u80c3\u4e0d\u8212\u670d",
            "\u4e0d\u8212\u670d",
            "\u96be\u53d7",
        )
        lowered = text.casefold()
        return any(marker in lowered for marker in markers)

    def _is_behavior_meta_instruction(self, text: str) -> bool:
        markers = (
            "\u592a\u50cf\u5ba2\u670d",
            "\u8bf4\u4eba\u8bdd",
            "\u4e0d\u8981\u53ea\u56de",
            "\u522b\u53ea\u56de",
            "\u591a\u8bf4\u51e0\u4e2a\u5b57",
            "\u4e0d\u4f1a\u804a\u5929",
            "\u7b54\u975e\u6240\u95ee",
            "\u522b\u626f",
            "\u4e0d\u8981\u626f",
            "\u4e71\u626f",
            "\u522b\u5ffd\u7136",
            "\u4e0d\u8981\u5ffd\u7136",
            "\u65e7\u4e66\u5c01\u9762",
            "\u56de\u590d\u6a21\u677f",
            "\u522b\u50cf\u673a\u5668\u4eba",
            "\u673a\u5668\u4eba\u90a3\u79cd\u8bed\u6c14",
            "\u4e0d\u8981\u5b89\u6170\u673a\u5668\u4eba",
            "\u522b\u5b89\u6170\u673a\u5668\u4eba",
            "\u522b\u5f00\u65b0\u8bdd\u9898",
            "\u4e0a\u4e0b\u6587\u4e0d\u5bf9",
            "\u6ca1\u770b\u4e0a\u4e0b\u6587",
            "\u6ca1\u6709\u4e0a\u4e0b\u6587",
            "\u6ca1\u770b\u61c2",
        )
        lowered = text.casefold()
        return any(marker in lowered for marker in markers)

    def _meal_or_status_memory(self, text: str) -> list[MemoryCapture]:
        patterns = (
            r"\b(?:i|we)\s+(?:had|ate)\s+(?P<object>[^.!?\n]{2,120})",
            r"\b(?:i|we)\s+had\s+(?P<object>breakfast|lunch|dinner)\b",
            r"(?:我|咱|我们)?(?:早饭|早餐|午饭|午餐|晚饭|晚餐)?(?:吃了|刚吃了|刚吃完|可能吃|想吃)"
            r"(?P<object>[^。！？\n]{1,80})",
            r"(?:我|咱|我们)?(?P<object>早上没吃饭|没吃饭|胃空|胃不舒服|不舒服|有点困|很困|困了|很烦|有点烦)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            obj = self._clean_fragment(match.group("object"))
            if not obj:
                continue
            return [
                MemoryCapture(
                    kind="working_context",
                    summary=f"recent personal context: {obj}",
                    confidence=0.5,
                    scope="short_term",
                    reason="recent_status_or_meal",
                    ttl_seconds=self.SHORT_TERM_TTL_SECONDS,
                )
            ]
        return []

    def _has_time_marker(self, text: str) -> bool:
        return bool(
            re.search(
                r"\b(today|tomorrow|tonight|this\s+week|next\s+week|on\s+\w+day|"
                r"\d{1,2}/\d{1,2}|\d{4}-\d{1,2}-\d{1,2})\b|"
                r"(今天|明天|后天|今晚|下午|上午|晚上|周末|下周|这周|[0-9]{1,2}月[0-9]{1,2}日)",
                text,
                re.IGNORECASE,
            )
        )

    def _dedupe(self, captures: list[MemoryCapture]) -> list[MemoryCapture]:
        seen: set[tuple[str, str]] = set()
        result: list[MemoryCapture] = []
        for capture in captures:
            key = (capture.kind, capture.summary.casefold())
            if key in seen:
                continue
            seen.add(key)
            result.append(capture)
        return result

    def _normalize(self, message: str) -> str:
        return re.sub(r"\s+", " ", message.strip())

    def _clean_fragment(self, value: str) -> str:
        return self._normalize(value).strip(" ：:，,。.!！？?；;、")
