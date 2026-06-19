from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

from local_qq_agent.config import WebConfig


@dataclass(frozen=True)
class BrowserReadResult:
    ok: bool
    url: str
    title: str
    text: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BrowserReader:
    def __init__(self, config: WebConfig) -> None:
        self.config = config

    async def read(self, url: str) -> BrowserReadResult:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not self._is_allowed(host):
            return BrowserReadResult(
                ok=False,
                url=url,
                title="",
                text="",
                reason=f"domain_not_allowlisted: {host}",
            )

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return BrowserReadResult(
                ok=False,
                url=url,
                title="",
                text="",
                reason="playwright is not installed",
            )

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.config.browser_timeout_seconds * 1000)
                title = await page.title()
                text = await page.locator("body").inner_text(timeout=self.config.browser_timeout_seconds * 1000)
            finally:
                await browser.close()

        return BrowserReadResult(
            ok=True,
            url=url,
            title=title.strip(),
            text=self._clean_text(text),
            reason="read",
        )

    def _is_allowed(self, host: str) -> bool:
        host = host.casefold()
        for domain in self.config.allowlisted_domains:
            normalized = domain.casefold()
            if host == normalized or host.endswith(f".{normalized}"):
                return True
        return False

    def _clean_text(self, text: str) -> str:
        blocked_phrases = (
            "ignore previous instructions",
            "忽略之前",
            "system prompt",
            "系统提示词",
        )
        lines: list[str] = []
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            lowered = line.casefold()
            if any(phrase in lowered for phrase in blocked_phrases):
                continue
            lines.append(line)
            if sum(len(item) for item in lines) > 4000:
                break
        return "\n".join(lines)[:4000]

