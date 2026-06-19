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
        completion_tokens = _token_count(usage.get("completion_tokens"))
        total_tokens = _token_count(usage.get("total_tokens")) or prompt_tokens + completion_tokens
        if total_tokens <= 0:
            return

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
            },
        )

    def snapshot(self) -> UsageSnapshot:
        today = datetime.now(UTC).date().isoformat()
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
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
        return UsageSnapshot(
            date=today,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            budget=self.budget,
            degrade_at_ratio=self.degrade_at_ratio,
        )


def _token_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float) and value > 0:
        return int(value)
    return 0
