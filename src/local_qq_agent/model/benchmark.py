from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import time
from typing import Any

from local_qq_agent.config import ConfigError, ModelConfig
from local_qq_agent.model.manager import restart_llama_server
from local_qq_agent.model.openai_client import OpenAICompatibleClient
from local_qq_agent.model.runtime import collect_model_runtime
from local_qq_agent.paths import ensure_parent, project_path


DEFAULT_OFFLOAD_PROFILES = (
    "qwen3-30b-iq2m-full-gpu",
    "qwen3-30b-iq2m-hybrid-high",
    "qwen3-30b-iq2m-hybrid-medium",
    "qwen3-30b-iq2m-cpu-ram",
)


@dataclass(frozen=True)
class BenchmarkPrompt:
    name: str
    messages: list[dict[str, str]]
    max_tokens: int


def benchmark_prompts() -> tuple[BenchmarkPrompt, ...]:
    long_context = "\n".join(
        f"context line {index}: The benchmark marker for this line is memory-{index:04d}."
        for index in range(1, 180)
    )
    return (
        BenchmarkPrompt(
            name="short_chat",
            messages=[
                {"role": "system", "content": "Reply briefly and naturally."},
                {"role": "user", "content": "用一句中文自然地回复：今天状态怎么样？"},
            ],
            max_tokens=48,
        ),
        BenchmarkPrompt(
            name="english_chat",
            messages=[
                {"role": "system", "content": "Reply briefly and naturally."},
                {"role": "user", "content": "Reply naturally in English: are you awake?"},
            ],
            max_tokens=48,
        ),
        BenchmarkPrompt(
            name="persona_call",
            messages=[
                {"role": "system", "content": "Reply as a group chat participant. Do not mention internals."},
                {"role": "user", "content": "有人在群里叫你的名字但没说别的，你会怎么回？"},
            ],
            max_tokens=64,
        ),
        BenchmarkPrompt(
            name="long_context",
            messages=[
                {"role": "system", "content": "Answer the question using the provided context."},
                {"role": "user", "content": f"{long_context}\n\nWhich marker is on context line 137?"},
            ],
            max_tokens=48,
        ),
        BenchmarkPrompt(
            name="tool_like_reasoning",
            messages=[
                {"role": "system", "content": "Give a concise technical answer without hidden reasoning."},
                {"role": "user", "content": "解释一下为什么部分模型层放在 RAM 会变慢，但仍然能运行。"},
            ],
            max_tokens=96,
        ),
    )


async def run_offload_benchmark(
    *,
    profile_names: list[str] | None = None,
    restore_profile: str | None = None,
) -> dict[str, Any]:
    selected_profiles = tuple(profile_names or DEFAULT_OFFLOAD_PROFILES)
    original_profile = restore_profile or ModelConfig.load().active_profile
    started_at = datetime.now().astimezone()
    report: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "profiles_requested": list(selected_profiles),
        "restore_profile": original_profile,
        "results": [],
        "restored": None,
    }

    try:
        for profile_name in selected_profiles:
            report["results"].append(await _benchmark_profile(profile_name))
    finally:
        report["restored"] = await _restore_profile(original_profile)

    artifact_path = _write_report(report)
    report["artifact_path"] = str(artifact_path)
    return report


async def _benchmark_profile(profile_name: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        config = ModelConfig.load_for_profile(profile_name)
    except ConfigError as error:
        return {
            "profile": profile_name,
            "ok": False,
            "reason": "profile_config_error",
            "error": str(error),
        }

    result: dict[str, Any] = {
        "profile": profile_name,
        "model": config.model,
        "server": {
            "n_ctx": config.server_n_ctx,
            "n_gpu_layers": config.server_n_gpu_layers,
            "n_batch": config.server_n_batch,
            "threads": config.server_n_threads,
            "threads_batch": config.server_n_threads_batch,
            "extra_args": list(config.server_extra_args),
        },
        "ok": False,
        "startup": None,
        "runtime_before": None,
        "runtime_after": None,
        "prompts": [],
    }

    startup = await asyncio.to_thread(restart_llama_server, config, wait_seconds=240)
    result["startup"] = startup
    if not startup.get("ready", {}).get("ok"):
        result["reason"] = "model_server_not_ready"
        result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        return result

    result["runtime_before"] = collect_model_runtime(config)
    client = OpenAICompatibleClient(config)
    for prompt in benchmark_prompts():
        result["prompts"].append(await _run_prompt(client, prompt))

    result["runtime_after"] = collect_model_runtime(config)
    result["ok"] = any(item.get("ok") for item in result["prompts"])
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    result["summary"] = _profile_summary(result)
    return result


async def _run_prompt(client: OpenAICompatibleClient, prompt: BenchmarkPrompt) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        reply = await client.chat(prompt.messages, max_tokens=prompt.max_tokens)
    except Exception as error:
        return {
            "name": prompt.name,
            "ok": False,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "error": str(error),
        }

    return {
        "name": prompt.name,
        "ok": True,
        "latency_seconds": round(reply.latency_seconds, 3),
        "model": reply.model,
        "content_preview": reply.content[:240],
        "usage": reply.usage,
        "tokens_per_second": reply.tokens_per_second,
    }


async def _restore_profile(profile_name: str) -> dict[str, Any]:
    try:
        config = ModelConfig.load_for_profile(profile_name)
    except ConfigError as error:
        return {"ok": False, "profile": profile_name, "reason": "profile_config_error", "error": str(error)}

    restored = await asyncio.to_thread(restart_llama_server, config, wait_seconds=240)
    return {"profile": profile_name, **restored}


def _profile_summary(result: dict[str, Any]) -> dict[str, Any]:
    successful = [item for item in result.get("prompts", []) if item.get("ok")]
    if not successful:
        return {"ok": False, "reason": "no_successful_prompts"}

    completion_rates = [
        item.get("tokens_per_second", {}).get("completion_tokens")
        for item in successful
        if item.get("tokens_per_second", {}).get("completion_tokens") is not None
    ]
    prompt_rates = [
        item.get("tokens_per_second", {}).get("prompt_tokens")
        for item in successful
        if item.get("tokens_per_second", {}).get("prompt_tokens") is not None
    ]
    return {
        "ok": True,
        "successful_prompts": len(successful),
        "avg_completion_tok_s": _average(completion_rates),
        "avg_prompt_tok_s": _average(prompt_rates),
        "avg_latency_seconds": _average([item["latency_seconds"] for item in successful]),
    }


def _write_report(report: dict[str, Any]):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = project_path(f"artifacts/runtime/model_offload_benchmark_{timestamp}.json")
    ensure_parent(path)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _average(values: list[float | int | None]) -> float | None:
    clean = [float(value) for value in values if isinstance(value, int | float)]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 3)
