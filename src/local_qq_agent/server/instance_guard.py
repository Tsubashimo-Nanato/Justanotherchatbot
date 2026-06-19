from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
import uuid

from local_qq_agent.paths import ensure_parent, project_path


@dataclass(frozen=True)
class AgentInstanceGuard:
    lease_path: Path = project_path("artifacts/runtime/active_agent_instance.json")
    instance_id: str = ""
    process_id: int = 0

    def __post_init__(self) -> None:
        if not self.instance_id:
            object.__setattr__(self, "instance_id", uuid.uuid4().hex)
        if not self.process_id:
            object.__setattr__(self, "process_id", os.getpid())

    def claim(self) -> dict[str, Any]:
        ensure_parent(self.lease_path)
        lease = self._lease_data()
        tmp_path = self.lease_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(lease, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.lease_path)
        return lease

    def current(self) -> dict[str, Any]:
        try:
            return json.loads(self.lease_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def is_current(self) -> bool:
        current = self.current()
        return (
            current.get("instance_id") == self.instance_id
            and int(current.get("process_id") or 0) == self.process_id
        )

    def status(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "process_id": self.process_id,
            "lease_path": str(self.lease_path),
            "is_current": self.is_current(),
            "current": self.current(),
        }

    def _lease_data(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "process_id": self.process_id,
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        }
