from __future__ import annotations

import json
import math
import time
from typing import Any

import httpx

from local_qq_agent.config import ModelConfig, ProviderConfig
from local_qq_agent.model.openai_client import ModelReply, tokens_per_second
from local_qq_agent.provider.tracing import ProviderTrace, ProviderTraceStore
from local_qq_agent.provider.usage import ProviderUsageLedger


DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["reply", "no_reply"]},
        "reply": {"type": "string"},
        "reason": {"type": "string"},
        "attention": {"type": "number"},
        "used_web": {"type": "boolean"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["title", "url"],
                "additionalProperties": False,
            },
        },
        "memory_update_suggestions": {"type": "array", "items": {"type": "string"}},
        "affinity_delta_suggestion": {
            "type": "object",
            "properties": {
                "delta": {"type": "number"},
                "reason": {"type": "string"},
                "confidence": {"type": "number"},
                "should_apply": {"type": "boolean"},
            },
            "required": ["delta", "reason", "confidence", "should_apply"],
            "additionalProperties": False,
        },
    },
    "required": [
        "action",
        "reply",
        "reason",
        "attention",
        "used_web",
        "sources",
        "memory_update_suggestions",
        "affinity_delta_suggestion",
    ],
    "additionalProperties": False,
}


class GrokClient:
    provider_name = "grok"
    supports_decision_call = True

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        model_config: ModelConfig,
        api_key: str,
        traces: ProviderTraceStore,
        usage: ProviderUsageLedger,
    ) -> None:
        self.provider_config = provider_config
        self.model_config = model_config
        self.api_key = api_key.strip()
        self.traces = traces
        self.usage = usage

    async def health(self) -> dict[str, Any]:
        if not self.api_key:
            return {
                "ok": False,
                "provider": self.provider_name,
                "model": self.provider_config.grok_model,
                "error": "XAI_API_KEY is not configured",
            }
        return {
            "ok": True,
            "provider": self.provider_name,
            "model": self.provider_config.grok_model,
            "base_url": self.provider_config.grok_base_url,
        }

    async def chat(self, messages: list[dict[str, str]], *, max_tokens: int | None = None) -> ModelReply:
        messages, input_budget = self._messages_within_input_budget(messages)
        payload = self._base_payload(messages, max_tokens=max_tokens)
        trace = self.traces.start(
            provider=self.provider_name,
            model=self.provider_config.grok_model,
            operation="chat",
            metadata={
                "message_count": len(messages),
                "max_tokens": payload.get("max_tokens"),
                "usage_requested": bool(payload.get("stream_options")),
                "input_budget": input_budget,
            },
        )
        return await self._stream_chat_with_compat(payload, trace=trace, operation="chat")

    async def chat_decision(self, messages: list[dict[str, str]], *, max_tokens: int | None = None) -> ModelReply:
        messages, input_budget = self._messages_within_input_budget(messages)
        payload = self._base_payload(messages, max_tokens=max_tokens)
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "qq_agent_decision",
                "schema": DECISION_SCHEMA,
                "strict": True,
            },
        }
        if self.provider_config.grok_enable_web_search:
            payload["tools"] = [{"type": "web_search"}]

        trace = self.traces.start(
            provider=self.provider_name,
            model=self.provider_config.grok_model,
            operation="decision",
            metadata={
                "message_count": len(messages),
                "max_tokens": payload.get("max_tokens"),
                "web_search_requested": bool(payload.get("tools")),
                "daily_usage": self.usage.snapshot().to_dict(),
                "input_budget": input_budget,
                "prompt_projection": messages,
            },
        )
        try:
            return await self._stream_chat_with_compat(payload, trace=trace, operation="decision")
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 400 or "tools" not in payload:
                raise
            trace.add(
                "web_search_retry",
                "Grok rejected the web_search tool on chat completions; retrying without the tool.",
                {"status_code": error.response.status_code, "body": error.response.text[:1000]},
            )
            payload = dict(payload)
            payload.pop("tools", None)
            return await self._stream_chat_with_compat(payload, trace=trace, operation="decision_retry_no_web")

    def cloud_loop_preflight(self) -> dict[str, Any]:
        usage = self.usage.snapshot()
        if (
            self.provider_config.require_duplicate_soak_for_cloud_loop
            and not self.provider_config.duplicate_soak_passed
        ):
            return {
                "ok": False,
                "reason": "duplicate_soak_required",
                "detail": "Cloud provider QQ loop is blocked until the duplicate soak test passes.",
                "usage": usage.to_dict(),
            }
        if not self.api_key:
            return {
                "ok": False,
                "reason": "xai_api_key_missing",
                "detail": "XAI_API_KEY is not configured.",
                "usage": usage.to_dict(),
            }
        return {
            "ok": True,
            "reason": "cloud_provider_ready",
            "usage": usage.to_dict(),
            "input_budget": {
                "per_message_input_token_budget": self.provider_config.per_message_input_token_budget,
                "enforce_input_budget": self.provider_config.enforce_input_budget,
            },
        }

    def _base_payload(self, messages: list[dict[str, str]], *, max_tokens: int | None) -> dict[str, Any]:
        if not messages:
            raise ValueError("messages must not be empty")
        if not self.api_key:
            raise RuntimeError("XAI_API_KEY is not configured")
        return {
            "model": self.provider_config.grok_model,
            "messages": messages,
            "temperature": self.model_config.temperature,
            "top_p": self.model_config.top_p,
            "max_tokens": max_tokens if max_tokens is not None else self.provider_config.grok_max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

    def _messages_within_input_budget(
        self,
        messages: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        original_estimate = estimate_input_tokens(messages)
        limit = int(self.provider_config.per_message_input_token_budget)
        metadata: dict[str, Any] = {
            "estimated_input_tokens": original_estimate,
            "per_message_input_token_budget": limit,
            "enforced": bool(self.provider_config.enforce_input_budget),
            "trimmed": False,
            "trimmed_messages": [],
        }
        if not self.provider_config.enforce_input_budget or limit <= 0 or original_estimate <= limit:
            return [dict(message) for message in messages], metadata

        trimmed = [dict(message) for message in messages]
        trimmed_indices: list[int] = []
        for _attempt in range(12):
            current_estimate = estimate_input_tokens(trimmed)
            if current_estimate <= limit:
                break
            largest_index = _largest_trim_candidate(trimmed)
            if largest_index is None:
                break
            content = str(trimmed[largest_index].get("content", ""))
            content_tokens = estimate_text_tokens(content)
            overflow = current_estimate - limit
            target_tokens = max(_minimum_keep_tokens(trimmed, largest_index), content_tokens - overflow - 128)
            if target_tokens >= content_tokens:
                target_tokens = max(_minimum_keep_tokens(trimmed, largest_index), math.floor(content_tokens * 0.82))
            replacement = trim_text_middle(content, target_tokens)
            if replacement == content:
                break
            trimmed[largest_index]["content"] = replacement
            trimmed_indices.append(largest_index)

        final_estimate = estimate_input_tokens(trimmed)
        metadata.update(
            {
                "estimated_input_tokens_after_trim": final_estimate,
                "trimmed": bool(trimmed_indices),
                "trimmed_messages": sorted(set(trimmed_indices)),
            }
        )
        return trimmed, metadata

    async def _stream_chat_with_compat(
        self,
        payload: dict[str, Any],
        *,
        trace: ProviderTrace,
        operation: str,
    ) -> ModelReply:
        try:
            return await self._stream_chat(payload, trace=trace, operation=operation)
        except httpx.HTTPStatusError as error:
            if not self._can_retry_without_stream_options(error, payload):
                raise
            trace.add(
                "stream_options_retry",
                "Provider rejected stream_options; retrying without streamed usage accounting.",
                {"status_code": error.response.status_code, "body": error.response.text[:1000]},
            )
            retry_payload = dict(payload)
            retry_payload.pop("stream_options", None)
            return await self._stream_chat(
                retry_payload,
                trace=trace,
                operation=f"{operation}_retry_no_stream_usage",
            )

    def _can_retry_without_stream_options(self, error: httpx.HTTPStatusError, payload: dict[str, Any]) -> bool:
        if error.response.status_code != 400 or "stream_options" not in payload:
            return False
        body = error.response.text.casefold()
        return "stream_options" in body or "extra inputs" in body or "unsupported" in body

    async def _stream_chat(self, payload: dict[str, Any], *, trace: ProviderTrace, operation: str) -> ModelReply:
        started_at = time.perf_counter()
        trace.add("api_request_started", "Streaming request started.", {"operation": operation})

        content_parts: list[str] = []
        usage: dict[str, Any] = {}
        model = self.provider_config.grok_model
        first_token_seen = False
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.provider_config.grok_timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.provider_config.grok_base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        trace.finish(error=body[:1000])
                        raise httpx.HTTPStatusError(
                            f"xAI request failed with HTTP {response.status_code}",
                            request=response.request,
                            response=response,
                        )

                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            break
                        chunk = _json_chunk(data)
                        if not chunk:
                            continue
                        model = str(chunk.get("model", model))
                        if isinstance(chunk.get("usage"), dict):
                            usage = dict(chunk["usage"])
                        for choice in chunk.get("choices", []) or []:
                            delta = choice.get("delta") or {}
                            if not isinstance(delta, dict):
                                continue
                            if delta.get("tool_calls"):
                                trace.add("tool_event", "Provider emitted a tool call delta.", {"tool_calls": delta.get("tool_calls")})
                            text = delta.get("content")
                            if not isinstance(text, str) or not text:
                                continue
                            if not first_token_seen:
                                first_token_seen = True
                                trace.add(
                                    "first_token",
                                    "First output token received.",
                                    {"latency_seconds": round(time.perf_counter() - started_at, 3)},
                                )
                            content_parts.append(text)
                            if len(content_parts) <= 20 or len(content_parts) % 50 == 0:
                                trace.add("output_delta", "Output delta received.", {"text": text})
        except Exception as error:
            trace.finish(error=str(error))
            raise

        latency = time.perf_counter() - started_at
        content = "".join(content_parts).strip()
        if not content:
            trace.finish(error="empty response content")
            raise RuntimeError("xAI response content was empty")

        trace.add(
            "final_output",
            "Streaming response completed.",
            {"usage": usage, "content_preview": content[:800]},
        )
        trace.finish()
        self.usage.record(
            provider=self.provider_name,
            model=model,
            usage=usage,
            trace_id=trace.trace_id,
            operation=operation,
        )
        return ModelReply(
            content=content,
            model=model,
            latency_seconds=latency,
            usage=usage,
            tokens_per_second=tokens_per_second(usage, latency),
            metadata={"trace_id": trace.trace_id, "provider": self.provider_name},
        )


def _json_chunk(data: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(data)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def estimate_input_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_text_tokens(str(message.get("content", ""))) + 4 for message in messages)


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    cjk_chars = sum(1 for char in text if "\u3400" <= char <= "\u9fff" or "\u3040" <= char <= "\u30ff")
    other_chars = max(len(text) - cjk_chars, 0)
    return max(1, cjk_chars + math.ceil(other_chars / 4))


def trim_text_middle(text: str, target_tokens: int) -> str:
    if estimate_text_tokens(text) <= target_tokens:
        return text
    if target_tokens <= 0:
        return "[trimmed by per-message input budget]"

    ratio = max(min(target_tokens / max(estimate_text_tokens(text), 1), 0.95), 0.05)
    keep_chars = max(int(len(text) * ratio), 240)
    if keep_chars >= len(text):
        return text

    marker = "\n[trimmed by per-message input budget]\n"
    head_chars = max(int((keep_chars - len(marker)) * 0.55), 80)
    tail_chars = max(keep_chars - len(marker) - head_chars, 80)
    if head_chars + tail_chars + len(marker) >= len(text):
        return text
    return f"{text[:head_chars].rstrip()}{marker}{text[-tail_chars:].lstrip()}"


def _largest_trim_candidate(messages: list[dict[str, str]]) -> int | None:
    candidates: list[tuple[int, int]] = []
    for index, message in enumerate(messages):
        content = str(message.get("content", ""))
        token_count = estimate_text_tokens(content)
        if token_count <= _minimum_keep_tokens(messages, index):
            continue
        candidates.append((token_count, index))
    if not candidates:
        return None
    return max(candidates)[1]


def _minimum_keep_tokens(messages: list[dict[str, str]], index: int) -> int:
    role = str(messages[index].get("role", ""))
    if index == len(messages) - 1 and role == "user":
        return 2200
    if role == "system":
        return 1800
    return 500
