from __future__ import annotations

import json

import _bootstrap  # noqa: F401

from local_qq_agent.config import QQConfig
from local_qq_agent.paths import ensure_parent, project_path
from local_qq_agent.qq import QQWindowAdapter


def main() -> None:
    adapter = QQWindowAdapter(QQConfig.load())
    result = adapter.probe()
    path = project_path("artifacts/qq_uia_probe.json")
    ensure_parent(path)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"QQ probe written: {path}")
    print(f"Controls captured: {result.get('control_count')}")


if __name__ == "__main__":
    main()
