from __future__ import annotations

import asyncio
import json
import time

import _bootstrap  # noqa: F401

from local_qq_agent.config import ModelConfig
from local_qq_agent.model import OpenAICompatibleClient
from local_qq_agent.paths import ensure_parent, project_path


async def run_smoke() -> dict[str, object]:
    config = ModelConfig.load()
    client = OpenAICompatibleClient(config)
    started_at = time.perf_counter()
    health = await client.health()

    report: dict[str, object] = {
        "health": health,
        "model": config.model,
        "base_url": config.base_url,
    }
    if not health.get("ok"):
        report["ok"] = False
        report["reason"] = "model_server_unavailable"
        return report

    try:
        reply = await client.chat(
            [
                {"role": "system", "content": "You are running a local model smoke test. Keep the answer short."},
                {"role": "user", "content": "Reply with one short sentence saying the local model is connected."},
            ]
        )
    except Exception as error:
        report["ok"] = False
        report["reason"] = "chat_completion_failed"
        report["error"] = str(error)
        return report
    elapsed = time.perf_counter() - started_at
    report.update(
        {
            "ok": True,
            "content": reply.content,
            "latency_seconds": round(reply.latency_seconds, 3),
            "total_seconds": round(elapsed, 3),
            "usage": reply.usage,
        }
    )
    return report


def main() -> None:
    report = asyncio.run(run_smoke())
    path = project_path("artifacts/model_smoke.json")
    ensure_parent(path)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Model smoke report written: {path}")


if __name__ == "__main__":
    main()
