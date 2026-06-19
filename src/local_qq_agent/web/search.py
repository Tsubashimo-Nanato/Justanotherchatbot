from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import httpx

from local_qq_agent.config import WebConfig


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    content: str
    engine: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class SearxngClient:
    def __init__(self, config: WebConfig) -> None:
        self.config = config

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.config.searxng_url}/")
            return {
                "ok": response.status_code < 500,
                "status_code": response.status_code,
                "url": self.config.searxng_url,
            }
        except httpx.HTTPError as error:
            return {"ok": False, "url": self.config.searxng_url, "error": str(error)}

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        query = query.strip()
        if not query:
            raise ValueError("search query must not be empty")

        params = {"q": query, "format": "json", "language": "auto"}
        async with httpx.AsyncClient(timeout=self.config.search_timeout_seconds) as client:
            response = await client.get(f"{self.config.searxng_url}/search", params=params)
            response.raise_for_status()

        body = response.json()
        raw_results = body.get("results", [])
        if not isinstance(raw_results, list):
            return []

        results: list[SearchResult] = []
        for item in raw_results[:limit]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip()
            if not url or not title:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    content=self._clean_text(str(item.get("content", ""))),
                    engine=str(item.get("engine", "")),
                )
            )
        return results

    def _clean_text(self, text: str) -> str:
        collapsed = " ".join(text.split())
        return collapsed[:600]

