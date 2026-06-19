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

        explicit = self._explicit_memory(text)
        if explicit:
            return explicit

        captures: list[MemoryCapture] = []
        captures.extend(self._mapping_memory(text))
        captures.extend(self._preference_memory(text))
        captures.extend(self._plan_memory(text))
        captures.extend(self._meal_or_status_memory(text))
        return self._dedupe(captures)

    def _explicit_memory(self, text: str) -> list[MemoryCapture]:
        markers = ("记住", "记一下", "remember")
        for marker in markers:
            index = text.casefold().find(marker.casefold())
            if index < 0:
                continue
            summary = text[index + len(marker) :].strip(" ：:，,。.!！?？")
            if summary:
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
        match = re.search(
            r"(?P<key>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})\s*"
            r"(?:represents|means|is|=|:|：|代表|是)\s*"
            r"(?P<value>[0-9][0-9A-Za-z_\-\s,，]*)",
            text,
            re.IGNORECASE,
        )
        if not match:
            return []

        key = match.group("key").strip()
        value = re.sub(r"\s+", " ", match.group("value")).strip(" ，,。.!！?？")
        if not key or not value:
            return []
        return [
            MemoryCapture(
                kind="fact",
                summary=f"{key} represents {value}",
                confidence=0.7,
                scope="long_term",
                reason="symbol_mapping",
            )
        ]

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
                r"我(?:很|超|特别|真的)?(?P<verb>喜欢吃|喜欢|爱吃|爱|讨厌|不喜欢)"
                r"(?P<object>[^。！？\n]{1,80})",
                "zh",
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
            if language == "favorite":
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

    def _plan_memory(self, text: str) -> list[MemoryCapture]:
        patterns = (
            r"\b(?:i|we)\s+(?:am\s+|are\s+|'m\s+|'re\s+)?(?:going|heading)\s+to\s+(?P<activity>[^.!?\n]{2,140})",
            r"\b(?:i|we)\s+(?:will|plan\s+to|have\s+to|need\s+to|am\s+going\s+to|are\s+going\s+to)\s+(?P<activity>[^.!?\n]{2,140})",
            r"\b(?:i|we)\s+have\s+(?:a|an)\s+(?P<activity>[^.!?\n]{2,100}?(?:appointment|doctor|doctors|dentist|class|exam))\b",
            r"我(?P<time>今天|明天|后天|今晚|下午|上午|晚上|周末|下周|这周|[0-9]{1,2}月[0-9]{1,2}日)?"
            r"(?:要|打算|准备|会|得|需要)去(?P<activity>[^。！？\n]{1,80})",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            activity = self._clean_fragment(match.group("activity"))
            if not activity:
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

    def _meal_or_status_memory(self, text: str) -> list[MemoryCapture]:
        patterns = (
            r"\b(?:i|we)\s+(?:had|ate)\s+(?P<object>[^.!?\n]{2,120})",
            r"\b(?:i|we)\s+had\s+(?P<object>breakfast|lunch|dinner)\b",
            r"我(?:早饭|早餐|午饭|午餐|晚饭|晚餐)?(?:吃了|刚吃了|刚吃完)"
            r"(?P<object>[^。！？\n]{1,80})",
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
        return self._normalize(value).strip(" ：:，,。.!！?？")
