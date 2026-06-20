from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

import httpx

from local_qq_agent.config import ModelConfig


@dataclass(frozen=True)
class ModelReply:
    content: str
    model: str
    latency_seconds: float
    usage: dict[str, Any]
    tokens_per_second: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class OpenAICompatibleClient:
    provider_name = "local"

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    async def health(self) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(
                    f"{self.config.base_url}/models",
                    headers=self._headers(),
                )
            latency = time.perf_counter() - started_at
            return {
                "ok": 200 <= response.status_code < 300,
                "status_code": response.status_code,
                "latency_seconds": round(latency, 3),
                "base_url": self.config.base_url,
                "model": self.config.model,
            }
        except httpx.HTTPError as error:
            return {
                "ok": False,
                "error": str(error),
                "base_url": self.config.base_url,
                "model": self.config.model,
            }

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        operation: str | None = None,
    ) -> ModelReply:
        if not messages:
            raise ValueError("messages must not be empty")

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "stream": False,
        }

        started_at = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.config.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()

        latency = time.perf_counter() - started_at
        body = response.json()
        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError("model response did not include choices")

        message = choices[0].get("message", {})
        content = str(message.get("content", "")).strip()
        if not content:
            raise RuntimeError("model response content was empty")

        usage = body.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        usage = dict(usage)

        return ModelReply(
            content=content,
            model=str(body.get("model", self.config.model)),
            latency_seconds=latency,
            usage=usage,
            tokens_per_second=tokens_per_second(usage, latency),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }


def tokens_per_second(usage: dict[str, Any], latency_seconds: float) -> dict[str, float]:
    if latency_seconds <= 0:
        return {}

    rates: dict[str, float] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        token_count = _positive_token_count(usage.get(key))
        if token_count is None:
            continue
        rates[key] = round(token_count / latency_seconds, 2)
    return rates


def _positive_token_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, int | float):
        return None
    if value <= 0:
        return None
    return int(value)
