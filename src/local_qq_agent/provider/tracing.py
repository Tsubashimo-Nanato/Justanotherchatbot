from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import time
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class TraceEvent:
    created_at: float
    stage: str
    detail: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderTrace:
    trace_id: str
    provider: str
    model: str
    operation: str
    created_at: float
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[TraceEvent] = field(default_factory=list)
    completed_at: float | None = None
    error: str = ""

    def add(self, stage: str, detail: str, metadata: dict[str, Any] | None = None) -> None:
        self.events.append(
            TraceEvent(
                created_at=time.time(),
                stage=stage,
                detail=detail,
                metadata=_compact_metadata(metadata or {}),
            )
        )

    def finish(self, *, error: str = "") -> None:
        self.completed_at = time.time()
        self.error = error

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        events = self.events[-20:] if compact else self.events
        return {
            "trace_id": self.trace_id,
            "provider": self.provider,
            "model": self.model,
            "operation": self.operation,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": round((self.completed_at or time.time()) - self.created_at, 3),
            "error": self.error,
            "metadata": _compact_metadata(self.metadata) if compact else self.metadata,
            "events": [event.to_dict() for event in events],
        }


class ProviderTraceStore:
    def __init__(self, *, max_traces: int = 100) -> None:
        self._traces: deque[ProviderTrace] = deque(maxlen=max_traces)

    def start(
        self,
        *,
        provider: str,
        model: str,
        operation: str,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderTrace:
        trace = ProviderTrace(
            trace_id=str(uuid4()),
            provider=provider,
            model=model,
            operation=operation,
            created_at=time.time(),
            metadata=metadata or {},
        )
        trace.add("request_created", "Provider request trace created.")
        self._traces.append(trace)
        return trace

    def recent(self, *, limit: int = 20) -> list[dict[str, Any]]:
        traces = list(self._traces)[-max(limit, 1) :]
        return [trace.to_dict(compact=True) for trace in reversed(traces)]

    def get(self, trace_id: str) -> dict[str, Any] | None:
        for trace in reversed(self._traces):
            if trace.trace_id == trace_id:
                return trace.to_dict(compact=False)
        return None

    def latest(self) -> dict[str, Any] | None:
        if not self._traces:
            return None
        return self._traces[-1].to_dict(compact=True)


def _compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in {"api_key", "authorization"}:
            continue
        result[str(key)] = _compact_value(value)
    return result


def _compact_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 1600 else f"{value[:1600]}... [truncated {len(value) - 1600} chars]"
    if isinstance(value, list):
        return [_compact_value(item) for item in value[:80]]
    if isinstance(value, dict):
        return {str(key): _compact_value(item) for key, item in value.items()}
    return value
