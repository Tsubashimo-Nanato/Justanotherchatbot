from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from local_qq_agent.memory import SQLiteMemoryStore


@dataclass(frozen=True)
class UsageSnapshot:
    date: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    cost_in_usd_ticks: int
    source_count: int
    tool_count: int
    budget: int
    degrade_at_ratio: float

    @property
    def used_ratio(self) -> float:
        if self.budget <= 0:
            return 0.0
        return self.total_tokens / self.budget

    @property
    def degraded(self) -> bool:
        return self.used_ratio >= self.degrade_at_ratio

    @property
    def exhausted(self) -> bool:
        return self.used_ratio >= 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost_in_usd_ticks": self.cost_in_usd_ticks,
            "cost_usd": round(self.cost_in_usd_ticks / 10_000_000_000, 8),
            "source_count": self.source_count,
            "tool_count": self.tool_count,
            "budget": self.budget,
            "used_ratio": round(self.used_ratio, 4),
            "degrade_at_ratio": self.degrade_at_ratio,
            "degraded": self.degraded,
            "exhausted": self.exhausted,
        }


class ProviderUsageLedger:
    def __init__(self, store: SQLiteMemoryStore, *, budget: int, degrade_at_ratio: float) -> None:
        self.store = store
        self.budget = budget
        self.degrade_at_ratio = degrade_at_ratio

    def record(
        self,
        *,
        provider: str,
        model: str,
        usage: dict[str, Any],
        trace_id: str = "",
        operation: str = "chat",
    ) -> None:
        prompt_tokens = _token_count(usage.get("prompt_tokens"))
        if prompt_tokens <= 0:
            prompt_tokens = _token_count(usage.get("input_tokens"))
        completion_tokens = _token_count(usage.get("completion_tokens"))
        if completion_tokens <= 0:
            completion_tokens = _token_count(usage.get("output_tokens"))
        total_tokens = _token_count(usage.get("total_tokens")) or prompt_tokens + completion_tokens
        if total_tokens <= 0:
            return
        prompt_details = _details(usage, "prompt_tokens_details", "input_tokens_details")
        completion_details = _details(usage, "completion_tokens_details", "output_tokens_details")
        cached_tokens = _token_count(prompt_details.get("cached_tokens"))
        reasoning_tokens = _token_count(completion_details.get("reasoning_tokens"))
        cost_ticks = _token_count(usage.get("cost_in_usd_ticks"))
        source_count = _token_count(usage.get("num_sources_used"))
        tool_count = _token_count(usage.get("num_server_side_tools_used"))

        self.store.append_event(
            source="provider",
            kind="provider_usage",
            content=f"{provider}:{model}:{total_tokens}",
            metadata={
                "provider": provider,
                "model": model,
                "operation": operation,
                "trace_id": trace_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cached_tokens": cached_tokens,
                "reasoning_tokens": reasoning_tokens,
                "cost_in_usd_ticks": cost_ticks,
                "source_count": source_count,
                "tool_count": tool_count,
                "raw_usage": usage,
            },
        )

    def snapshot(self) -> UsageSnapshot:
        today = datetime.now(UTC).date().isoformat()
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        cached_tokens = 0
        reasoning_tokens = 0
        cost_ticks = 0
        source_count = 0
        tool_count = 0
        try:
            events = self.store.recent_events(limit=2000, newest_first=True)
        except Exception:
            events = []
        for event in events:
            if event.kind != "provider_usage":
                continue
            if not event.created_at.startswith(today):
                continue
            metadata = event.metadata or {}
            prompt_tokens += _token_count(metadata.get("prompt_tokens"))
            completion_tokens += _token_count(metadata.get("completion_tokens"))
            total_tokens += _token_count(metadata.get("total_tokens"))
            cached_tokens += _token_count(metadata.get("cached_tokens"))
            reasoning_tokens += _token_count(metadata.get("reasoning_tokens"))
            cost_ticks += _token_count(metadata.get("cost_in_usd_ticks"))
            source_count += _token_count(metadata.get("source_count"))
            tool_count += _token_count(metadata.get("tool_count"))
        return UsageSnapshot(
            date=today,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            cost_in_usd_ticks=cost_ticks,
            source_count=source_count,
            tool_count=tool_count,
            budget=self.budget,
            degrade_at_ratio=self.degrade_at_ratio,
        )


def _token_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float) and value > 0:
        return int(value)
    return 0


def _details(usage: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, dict):
            return value
    return {}
