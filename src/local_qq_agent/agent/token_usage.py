from __future__ import annotations

from copy import deepcopy
from typing import Any


LOCAL_OPERATIONS = ("gate", "placeholder", "final", "raw_local", "rewrite", "total")
API_OPERATIONS = ("final", "web", "rewrite", "decision", "total")


def empty_token_usage() -> dict[str, Any]:
    return {
        "local": {operation: _empty_local_usage() for operation in LOCAL_OPERATIONS},
        "api": {operation: _empty_api_usage() for operation in API_OPERATIONS},
    }


def usage_from_reply(reply: Any, *, scope: str) -> dict[str, Any]:
    usage = getattr(reply, "usage", {}) or {}
    latency = getattr(reply, "latency_seconds", None)
    if scope == "api":
        return api_usage(usage, latency_seconds=latency)
    return local_usage(usage, latency_seconds=latency)


def local_usage(usage: dict[str, Any], *, latency_seconds: float | None = None) -> dict[str, Any]:
    result = _empty_local_usage()
    result["prompt"] = _int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    result["completion"] = _int(usage.get("completion_tokens") or usage.get("output_tokens"))
    result["total"] = _int(usage.get("total_tokens")) or result["prompt"] + result["completion"]
    if latency_seconds is not None:
        result["latency_seconds"] = round(float(latency_seconds), 3)
    return result


def api_usage(usage: dict[str, Any], *, latency_seconds: float | None = None) -> dict[str, Any]:
    result = _empty_api_usage()
    result["input"] = _int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    result["output"] = _int(usage.get("completion_tokens") or usage.get("output_tokens"))
    result["total"] = _int(usage.get("total_tokens")) or result["input"] + result["output"]

    prompt_details = _details(usage, "prompt_tokens_details", "input_tokens_details")
    completion_details = _details(usage, "completion_tokens_details", "output_tokens_details")
    result["cached"] = _int(prompt_details.get("cached_tokens"))
    result["reasoning"] = _int(completion_details.get("reasoning_tokens"))
    result["cost_ticks"] = _int(usage.get("cost_in_usd_ticks"))
    if latency_seconds is not None:
        result["latency_seconds"] = round(float(latency_seconds), 3)
    return result


def add_usage(
    token_usage: dict[str, Any] | None,
    *,
    scope: str,
    operation: str,
    usage: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(token_usage) if token_usage else empty_token_usage()
    if scope == "api":
        operation = operation if operation in result["api"] else "final"
        _add_api(result["api"][operation], usage)
        _add_api(result["api"]["total"], usage)
        return result

    operation = operation if operation in result["local"] else "final"
    _add_local(result["local"][operation], usage)
    _add_local(result["local"]["total"], usage)
    return result


def merge_token_usage(*items: dict[str, Any] | None) -> dict[str, Any]:
    result = empty_token_usage()
    for item in items:
        if not item:
            continue
        for operation, usage in (item.get("local") or {}).items():
            if operation not in result["local"]:
                result["local"][operation] = _empty_local_usage()
            _add_local(result["local"][operation], usage)
        for operation, usage in (item.get("api") or {}).items():
            if operation not in result["api"]:
                result["api"][operation] = _empty_api_usage()
            _add_api(result["api"][operation], usage)
    return result


def scope_for_client(client: Any) -> str:
    return "api" if str(getattr(client, "provider_name", "")).casefold() == "grok" else "local"


def _empty_local_usage() -> dict[str, Any]:
    return {"prompt": 0, "completion": 0, "total": 0, "latency_seconds": 0}


def _empty_api_usage() -> dict[str, Any]:
    return {
        "input": 0,
        "output": 0,
        "total": 0,
        "cached": 0,
        "reasoning": 0,
        "cost_ticks": 0,
        "latency_seconds": 0,
    }


def _add_local(target: dict[str, Any], usage: dict[str, Any]) -> None:
    for key in ("prompt", "completion", "total"):
        target[key] = _int(target.get(key)) + _int(usage.get(key))
    target["latency_seconds"] = round(_float(target.get("latency_seconds")) + _float(usage.get("latency_seconds")), 3)


def _add_api(target: dict[str, Any], usage: dict[str, Any]) -> None:
    for key in ("input", "output", "total", "cached", "reasoning", "cost_ticks"):
        target[key] = _int(target.get(key)) + _int(usage.get(key))
    target["latency_seconds"] = round(_float(target.get("latency_seconds")) + _float(usage.get("latency_seconds")), 3)


def _details(usage: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float) and value > 0:
        return int(value)
    return 0


def _float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float) and value > 0:
        return float(value)
    return 0.0
