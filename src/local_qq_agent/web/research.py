from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import re
import time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from local_qq_agent.web.browser import BrowserReader
from local_qq_agent.web.search import SearchResult, SearxngClient


@dataclass(frozen=True)
class WebSource:
    title: str
    url: str
    content: str
    source_type: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class WebContext:
    used: bool
    query: str
    context: str
    sources: list[WebSource] = field(default_factory=list)
    latency_seconds: float = 0.0
    reason: str = ""
    error: str = ""
    local_time_used: bool = False
    search_used: bool = False
    browser_used: bool = False

    def to_metadata(self) -> dict[str, Any]:
        return {
            "web_used": self.used,
            "web_query": self.query,
            "web_sources": [source.to_dict() for source in self.sources],
            "web_source_count": len(self.sources),
            "tool_latency_seconds": self.latency_seconds,
            "web_reason": self.reason,
            "web_error": self.error,
            "local_time_used": self.local_time_used,
            "search_used": self.search_used,
            "browser_used": self.browser_used,
        }


class WebResearcher:
    def __init__(self, search: SearxngClient, browser: BrowserReader) -> None:
        self.search = search
        self.browser = browser

    def should_search(self, message: str) -> bool:
        text = message.casefold()
        triggers = (
            "查一下",
            "搜索",
            "搜一下",
            "维基",
            "wikipedia",
            "wiki",
            "新闻",
            "最新",
            "今天",
            "明天",
            "现在",
            "天气",
            "气温",
            "温度",
            "下雨",
            "降雨",
            "预报",
            "日期",
            "几号",
            "几点",
            "current",
            "latest",
            "news",
            "weather",
            "forecast",
            "temperature",
            "rain",
            "today",
            "tomorrow",
            "now",
        )
        return any(trigger in text for trigger in triggers)

    async def answer_context(self, message: str) -> WebContext:
        started_at = time.perf_counter()
        message = message.strip()
        if not self.should_search(message):
            return WebContext(used=False, query="", context="", reason="not_needed")

        local = self._local_time_context(message)
        query = self._search_query(message)
        sources: list[WebSource] = []
        errors: list[str] = []
        search_used = False

        if query:
            search_used = True
            try:
                results = await self.search.search(query, limit=5)
                sources.extend(self._search_sources(results))
                sources.extend(await self._read_sources(results))
            except Exception as error:
                errors.append(str(error))

        context = self._format_context(local, sources)
        browser_used = any(source.source_type == "browser_read" for source in sources)
        used = search_used or browser_used
        return WebContext(
            used=used,
            query=query,
            context=context,
            sources=sources[:5],
            latency_seconds=round(time.perf_counter() - started_at, 3),
            reason="searched" if query else "local_time",
            error="; ".join(errors),
            local_time_used=bool(local),
            search_used=search_used,
            browser_used=browser_used,
        )

    def _local_time_context(self, message: str) -> str:
        text = message.casefold()
        if not any(trigger in text for trigger in ("今天", "日期", "几号", "几点", "现在", "today", "now", "date", "time")):
            return ""

        requested_timezone_name = "Asia/Tokyo"
        timezone_label = requested_timezone_name
        try:
            now = datetime.now(ZoneInfo(requested_timezone_name))
        except ZoneInfoNotFoundError:
            now = datetime.now().astimezone()
            timezone_label = f"{requested_timezone_name} (local fallback: {now.tzinfo or 'local'})"
        return (
            "本地时间资料:\n"
            f"- 时区: {timezone_label}\n"
            f"- 当前日期: {now.date().isoformat()}\n"
            f"- 当前时间: {now.strftime('%H:%M:%S')}\n"
            f"- 星期: {now.strftime('%A')}"
        )

    def _search_query(self, message: str) -> str:
        compact = " ".join(message.split())
        replacements = (
            ".enforce",
            ".detail",
            ".debug",
            ".ignore",
            ".think",
        )
        for marker in replacements:
            compact = compact.replace(marker, " ")
        compact = re.sub(r"\s+[0-3]\s*$", "", compact).strip()

        if "维基" in compact or "wikipedia" in compact.casefold() or "wiki" in compact.casefold():
            return f"{compact} site:wikipedia.org"
        if "新闻" in compact or "latest" in compact.casefold() or "news" in compact.casefold():
            return compact
        weather_markers = (
            "天气",
            "气温",
            "温度",
            "下雨",
            "降雨",
            "预报",
            "weather",
            "forecast",
            "temperature",
            "rain",
        )
        if any(marker in compact.casefold() for marker in weather_markers):
            return compact
        if self._local_time_context(compact) and len(compact) <= 20:
            return ""
        return compact

    def _search_sources(self, results: list[SearchResult]) -> list[WebSource]:
        sources: list[WebSource] = []
        for result in results[:3]:
            if not result.content:
                continue
            sources.append(
                WebSource(
                    title=result.title,
                    url=result.url,
                    content=result.content,
                    source_type="search_result",
                )
            )
        return sources

    async def _read_sources(self, results: list[SearchResult]) -> list[WebSource]:
        sources: list[WebSource] = []
        for result in results:
            if len(sources) >= 2:
                break
            read = await self.browser.read(result.url)
            if not read.ok or not read.text:
                continue
            sources.append(
                WebSource(
                    title=read.title or result.title,
                    url=read.url,
                    content=read.text[:1600],
                    source_type="browser_read",
                )
            )
        return sources

    def _format_context(self, local: str, sources: list[WebSource]) -> str:
        parts: list[str] = []
        if local:
            parts.append(local)
        if sources:
            lines = ["联网资料:"]
            for index, source in enumerate(sources[:5], start=1):
                lines.append(f"[{index}] {source.title}")
                lines.append(f"URL: {source.url}")
                lines.append(source.content[:1600])
            parts.append("\n".join(lines))
        return "\n\n".join(parts).strip()
