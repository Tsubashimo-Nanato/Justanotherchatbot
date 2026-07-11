from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml

from local_qq_agent.paths import project_path


class ConfigError(ValueError):
    pass


def read_yaml(path: str | Path) -> dict[str, Any]:
    resolved = project_path(path)
    if not resolved.exists():
        raise ConfigError(f"config file not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}

    if not isinstance(value, dict):
        raise ConfigError(f"config file must contain a mapping: {resolved}")
    return value


def require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a mapping")
    return value


def require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty string")
    return value


def optional_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be a boolean")
    return value


def optional_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or value < 0:
        raise ConfigError(f"{key} must be a non-negative integer")
    return value


def optional_signed_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    return value


def optional_float(data: dict[str, Any], key: str, default: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ConfigError(f"{key} must be a non-negative number")
    return float(value)


def optional_string_tuple(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{key} must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


def optional_choice(data: dict[str, Any], key: str, default: str, choices: set[str]) -> str:
    value = str(data.get(key, default)).strip().casefold()
    if value not in choices:
        raise ConfigError(f"{key} must be one of: {', '.join(sorted(choices))}")
    return value


def optional_path(data: dict[str, Any], key: str) -> Path | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a path string")
    return project_path(value)


@dataclass(frozen=True)
class ModelConfig:
    active_profile: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    temperature: float
    top_p: float
    max_tokens: int
    context_tokens_target: int
    context_tokens_fallback: int
    download_repo_id: str
    download_filename: str
    download_target_path: Path
    server_host: str
    server_port: int
    server_n_ctx: int
    server_n_gpu_layers: int
    server_n_batch: int
    server_n_threads: int | None
    server_n_threads_batch: int | None
    server_extra_args: tuple[str, ...]

    @classmethod
    def load(cls, path: str | Path = "config/model.yaml") -> "ModelConfig":
        return cls.load_for_profile(None, path)

    @classmethod
    def load_for_profile(cls, profile_name: str | None, path: str | Path = "config/model.yaml") -> "ModelConfig":
        raw = read_yaml(path)
        requested_profile = str(profile_name or raw.get("active_profile", "")).strip()
        profiles = raw.get("profiles")
        if isinstance(profiles, dict) and profiles:
            if not requested_profile:
                requested_profile = str(next(iter(profiles)))
            profile_raw = profiles.get(requested_profile)
            if not isinstance(profile_raw, dict):
                raise ConfigError(f"model profile not found: {requested_profile}")
            raw = {**raw, **profile_raw}
        else:
            requested_profile = "default"

        provider = require_mapping(raw, "provider")
        generation = require_mapping(raw, "generation")
        download = require_mapping(raw, "download")
        server = raw.get("server", {})
        if server is None:
            server = {}
        if not isinstance(server, dict):
            raise ConfigError("server must be a mapping")

        return cls(
            active_profile=requested_profile,
            base_url=require_string(provider, "base_url").rstrip("/"),
            api_key=str(provider.get("api_key", "local-demo")),
            model=require_string(provider, "model"),
            timeout_seconds=optional_int(provider, "timeout_seconds", 90),
            temperature=float(generation.get("temperature", 0.7)),
            top_p=float(generation.get("top_p", 0.9)),
            max_tokens=optional_int(generation, "max_tokens", 384),
            context_tokens_target=optional_int(generation, "context_tokens_target", 32768),
            context_tokens_fallback=optional_int(generation, "context_tokens_fallback", 16384),
            download_repo_id=require_string(download, "repo_id"),
            download_filename=require_string(download, "filename"),
            download_target_path=project_path(require_string(download, "target_path")),
            server_host=str(server.get("host", "127.0.0.1")),
            server_port=optional_int(server, "port", 18080),
            server_n_ctx=optional_int(server, "n_ctx", optional_int(generation, "context_tokens_target", 8192)),
            server_n_gpu_layers=optional_signed_int(server, "n_gpu_layers", -1),
            server_n_batch=optional_int(server, "n_batch", 512),
            server_n_threads=_optional_server_int(server, "threads"),
            server_n_threads_batch=_optional_server_int(server, "threads_batch"),
            server_extra_args=_server_extra_args(server),
        )

    @classmethod
    def profiles(cls, path: str | Path = "config/model.yaml") -> dict[str, dict[str, Any]]:
        raw = read_yaml(path)
        profiles = raw.get("profiles")
        if not isinstance(profiles, dict) or not profiles:
            config = cls.load(path)
            return {
                config.active_profile: {
                    "provider": {"base_url": config.base_url, "model": config.model},
                    "generation": {
                        "context_tokens_target": config.context_tokens_target,
                        "context_tokens_fallback": config.context_tokens_fallback,
                        "max_tokens": config.max_tokens,
                    },
                    "download": {
                        "repo_id": config.download_repo_id,
                        "filename": config.download_filename,
                        "target_path": str(config.download_target_path),
                    },
                }
            }
        return profiles


@dataclass(frozen=True)
class PersonaConfig:
    name: str
    language: str
    summary: str
    style_rules: tuple[str, ...]
    ooc_triggers: tuple[str, ...]
    fallback_reply: str
    profile_documents: tuple[Path, ...] = ()
    style_learning_enabled: bool = False
    style_learning_target_user: str = ""
    base_anchor_weight: str = "normal"
    proactive_topic_bias: float = 0.35
    style_learning_auto_distill: bool = False
    style_learning_generated_anchor_path: Path | None = None
    style_learning_run_log_dir: Path | None = None

    @classmethod
    def load(cls, path: str | Path = "config/persona.yaml") -> "PersonaConfig":
        raw = read_yaml(path)
        style_rules = raw.get("style_rules", [])
        ooc_triggers = raw.get("ooc_triggers", [])
        profile_documents = raw.get("profile_documents", [])
        style_learning = raw.get("style_learning", {})
        if style_learning is None:
            style_learning = {}
        if not isinstance(style_learning, dict):
            raise ConfigError("style_learning must be a mapping")
        if not isinstance(style_rules, list) or not all(isinstance(item, str) for item in style_rules):
            raise ConfigError("style_rules must be a list of strings")
        if not isinstance(ooc_triggers, list) or not all(isinstance(item, str) for item in ooc_triggers):
            raise ConfigError("ooc_triggers must be a list of strings")
        if not isinstance(profile_documents, list) or not all(isinstance(item, str) for item in profile_documents):
            raise ConfigError("profile_documents must be a list of strings")

        return cls(
            name=require_string(raw, "name"),
            language=str(raw.get("language", "zh-CN")),
            summary=require_string(raw, "summary"),
            style_rules=tuple(style_rules),
            ooc_triggers=tuple(ooc_triggers),
            fallback_reply=require_string(raw, "fallback_reply"),
            profile_documents=tuple(project_path(item) for item in profile_documents),
            style_learning_enabled=optional_bool(style_learning, "enabled", False),
            style_learning_target_user=str(style_learning.get("target_user", "")).strip(),
            base_anchor_weight=str(style_learning.get("base_anchor_weight", "normal")).strip() or "normal",
            proactive_topic_bias=min(max(optional_float(style_learning, "proactive_topic_bias", 0.35), 0.0), 1.0),
            style_learning_auto_distill=optional_bool(style_learning, "auto_distill_on_start", False),
            style_learning_generated_anchor_path=optional_path(style_learning, "generated_anchor_path"),
            style_learning_run_log_dir=optional_path(style_learning, "run_log_dir"),
        )


@dataclass(frozen=True)
class MemoryConfig:
    database_path: Path
    recent_event_limit: int
    memory_search_limit: int
    long_term_memory_kinds: tuple[str, ...]

    @classmethod
    def load(cls, path: str | Path = "config/memory.yaml") -> "MemoryConfig":
        raw = read_yaml(path)
        kinds = raw.get("long_term_memory_kinds", [])
        if not isinstance(kinds, list) or not all(isinstance(item, str) for item in kinds):
            raise ConfigError("long_term_memory_kinds must be a list of strings")

        return cls(
            database_path=project_path(require_string(raw, "database_path")),
            recent_event_limit=optional_int(raw, "recent_event_limit", 30),
            memory_search_limit=optional_int(raw, "memory_search_limit", 8),
            long_term_memory_kinds=tuple(kinds),
        )


@dataclass(frozen=True)
class OneBotConfig:
    reverse_ws_path: str
    access_token: str
    target_group_id: str
    target_group_name: str
    target_sender_name: str
    bot_sender_name: str
    max_messages_per_tick: int
    ignore_existing_on_start: bool
    action_timeout_seconds: float = 8.0
    send_timeout_seconds: float = 15.0
    duplicate_suppression_seconds: float = 3600.0
    turn_quiet_period_seconds: float = 6.0
    startup_scrollback_readable_messages: int = 30
    event_log_limit: int = 200
    bot_sender_aliases: tuple[str, ...] = ()

    @classmethod
    def load(cls, path: str | Path = "config/onebot.yaml") -> "OneBotConfig":
        raw = read_yaml(path)
        local_path = Path(path).with_name(f"{Path(path).stem}.local.yaml")
        if local_path.exists():
            raw = {**raw, **read_yaml(local_path)}
        return cls(
            reverse_ws_path=str(raw.get("reverse_ws_path", "/onebot/v11/ws")),
            access_token=os.getenv("ONEBOT_ACCESS_TOKEN", str(raw.get("access_token", ""))).strip(),
            target_group_id=str(raw.get("target_group_id", "")).strip(),
            target_group_name=str(raw.get("target_group_name", "")).strip(),
            target_sender_name=str(raw.get("target_sender_name", "")),
            bot_sender_name=str(raw.get("bot_sender_name", "")),
            max_messages_per_tick=optional_int(raw, "max_messages_per_tick", 2),
            ignore_existing_on_start=optional_bool(raw, "ignore_existing_on_start", True),
            action_timeout_seconds=optional_float(raw, "action_timeout_seconds", 8.0),
            send_timeout_seconds=optional_float(raw, "send_timeout_seconds", 15.0),
            duplicate_suppression_seconds=optional_float(raw, "duplicate_suppression_seconds", 3600.0),
            turn_quiet_period_seconds=optional_float(raw, "turn_quiet_period_seconds", 6.0),
            startup_scrollback_readable_messages=optional_int(raw, "startup_scrollback_readable_messages", 30),
            event_log_limit=optional_int(raw, "event_log_limit", 200),
            bot_sender_aliases=optional_string_tuple(raw, "bot_sender_aliases"),
        )


def save_onebot_group_selection(
    *,
    group_id: str,
    group_name: str,
    path: str | Path = "config/onebot.local.yaml",
) -> Path:
    selected_id = str(group_id).strip()
    if not selected_id:
        raise ValueError("group_id must not be empty")
    resolved = project_path(path)
    existing = read_yaml(resolved) if resolved.exists() else {}
    existing["target_group_id"] = selected_id
    existing["target_group_name"] = str(group_name).strip()
    resolved.write_text(
        yaml.safe_dump(existing, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return resolved


@dataclass(frozen=True)
class AutonomyConfig:
    mode: str
    min_seconds_between_messages: float
    max_messages_per_hour: int
    allow_spontaneous_topics: bool
    require_human_trigger_for_demo: bool
    spontaneous_min_idle_seconds: float = 900.0
    spontaneous_bot_cooldown_seconds: float = 1200.0
    spontaneous_backoff_seconds: float = 420.0
    spontaneous_token_capacity: float = 2.0
    spontaneous_token_refill_per_hour: float = 2.0

    @classmethod
    def load(cls, path: str | Path = "config/autonomy.yaml") -> "AutonomyConfig":
        raw = read_yaml(path)
        return cls(
            mode=str(raw.get("mode", "manual-demo")),
            min_seconds_between_messages=optional_float(raw, "min_seconds_between_messages", 90.0),
            max_messages_per_hour=optional_int(raw, "max_messages_per_hour", 12),
            allow_spontaneous_topics=optional_bool(raw, "allow_spontaneous_topics", False),
            require_human_trigger_for_demo=optional_bool(raw, "require_human_trigger_for_demo", True),
            spontaneous_min_idle_seconds=optional_float(raw, "spontaneous_min_idle_seconds", 900.0),
            spontaneous_bot_cooldown_seconds=optional_float(raw, "spontaneous_bot_cooldown_seconds", 1200.0),
            spontaneous_backoff_seconds=optional_float(raw, "spontaneous_backoff_seconds", 420.0),
            spontaneous_token_capacity=optional_float(raw, "spontaneous_token_capacity", 2.0),
            spontaneous_token_refill_per_hour=optional_float(raw, "spontaneous_token_refill_per_hour", 2.0),
        )


@dataclass(frozen=True)
class WebConfig:
    searxng_url: str
    search_timeout_seconds: int
    browser_timeout_seconds: int
    allowlisted_domains: tuple[str, ...]

    @classmethod
    def load(cls, path: str | Path = "config/web.yaml") -> "WebConfig":
        raw = read_yaml(path)
        domains = raw.get("allowlisted_domains", [])
        if not isinstance(domains, list) or not all(isinstance(item, str) for item in domains):
            raise ConfigError("allowlisted_domains must be a list of strings")

        return cls(
            searxng_url=require_string(raw, "searxng_url").rstrip("/"),
            search_timeout_seconds=optional_int(raw, "search_timeout_seconds", 20),
            browser_timeout_seconds=optional_int(raw, "browser_timeout_seconds", 20),
            allowlisted_domains=tuple(domains),
        )


def _optional_server_int(server: dict[str, Any], key: str) -> int | None:
    if key not in server or server.get(key) is None:
        return None
    return optional_signed_int(server, key, 0)


def _server_extra_args(server: dict[str, Any]) -> tuple[str, ...]:
    raw = server.get("extra_args", [])
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ConfigError("server.extra_args must be a list of strings")
    return tuple(item for item in raw if item.strip())


@dataclass(frozen=True)
class ProviderConfig:
    active_provider: str
    grok_base_url: str
    grok_model: str
    grok_timeout_seconds: int
    grok_max_tokens: int
    grok_enable_web_search: bool
    grok_endpoint: str
    grok_reasoning_simple_chat: str
    grok_reasoning_final_reply: str
    grok_reasoning_rewrite: str
    grok_reasoning_web_fact: str
    grok_reasoning_complex_reasoning: str
    grok_cache_enabled: bool
    grok_cache_scope: str
    daily_token_budget: int
    degrade_at_ratio: float
    per_message_input_token_budget: int
    enforce_input_budget: bool
    raw_local_max_tokens: int
    raw_local_temperature: float
    raw_local_top_p: float
    raw_local_stop: tuple[str, ...]
    raw_local_extra_payload: dict[str, Any]
    require_duplicate_soak_for_cloud_loop: bool
    duplicate_soak_passed: bool

    @classmethod
    def load(cls, path: str | Path = "config/provider.yaml") -> "ProviderConfig":
        raw = read_yaml(path)
        grok = raw.get("grok", {})
        if not isinstance(grok, dict):
            raise ConfigError("grok must be a mapping")
        reasoning = grok.get("reasoning", {})
        if reasoning is None:
            reasoning = {}
        if not isinstance(reasoning, dict):
            raise ConfigError("grok.reasoning must be a mapping")
        cache = grok.get("cache", {})
        if cache is None:
            cache = {}
        if not isinstance(cache, dict):
            raise ConfigError("grok.cache must be a mapping")
        budget = raw.get("budget", {})
        if not isinstance(budget, dict):
            raise ConfigError("budget must be a mapping")
        runtime = raw.get("runtime", {})
        if runtime is None:
            runtime = {}
        if not isinstance(runtime, dict):
            raise ConfigError("runtime must be a mapping")
        raw_local = raw.get("raw_local", {})
        if raw_local is None:
            raw_local = {}
        if not isinstance(raw_local, dict):
            raise ConfigError("raw_local must be a mapping")
        raw_local_stop = raw_local.get("stop", [])
        if raw_local_stop is None:
            raw_local_stop = []
        if not isinstance(raw_local_stop, list) or not all(isinstance(item, str) for item in raw_local_stop):
            raise ConfigError("raw_local.stop must be a list of strings")
        raw_local_extra = raw_local.get("extra_payload", {})
        if raw_local_extra is None:
            raw_local_extra = {}
        if not isinstance(raw_local_extra, dict):
            raise ConfigError("raw_local.extra_payload must be a mapping")
        safety = raw.get("safety", {})
        if not isinstance(safety, dict):
            raise ConfigError("safety must be a mapping")

        provider = str(raw.get("active_provider", "unloaded")).strip().casefold()
        if provider not in {"unloaded", "local", "local_raw", "qwen", "grok", "hybrid", "grok_responses", "hybrid_responses"}:
            raise ConfigError(f"unsupported provider: {provider}")
        reasoning_choices = {"none", "low", "medium", "high"}

        return cls(
            active_provider=provider,
            grok_base_url=str(grok.get("base_url", "https://api.x.ai/v1")).rstrip("/"),
            grok_model=str(grok.get("model", "grok-4.3")).strip() or "grok-4.3",
            grok_timeout_seconds=optional_int(grok, "timeout_seconds", 180),
            grok_max_tokens=optional_int(grok, "max_tokens", 512),
            grok_enable_web_search=optional_bool(grok, "enable_web_search", True),
            grok_endpoint=optional_choice(grok, "endpoint", "chat_completions", {"chat_completions", "responses"}),
            grok_reasoning_simple_chat=optional_choice(reasoning, "simple_chat", "none", reasoning_choices),
            grok_reasoning_final_reply=optional_choice(reasoning, "final_reply", "low", reasoning_choices),
            grok_reasoning_rewrite=optional_choice(reasoning, "rewrite", "none", reasoning_choices),
            grok_reasoning_web_fact=optional_choice(reasoning, "web_fact", "medium", reasoning_choices),
            grok_reasoning_complex_reasoning=optional_choice(
                reasoning,
                "complex_reasoning",
                "high",
                reasoning_choices,
            ),
            grok_cache_enabled=optional_bool(cache, "enabled", True),
            grok_cache_scope=str(cache.get("scope", "qq_group_session")).strip() or "qq_group_session",
            daily_token_budget=optional_int(
                budget,
                "smoke_daily_token_budget",
                optional_int(budget, "daily_token_budget", 1000000),
            ),
            degrade_at_ratio=min(max(optional_float(budget, "degrade_at_ratio", 0.8), 0.0), 1.0),
            per_message_input_token_budget=optional_int(runtime, "per_message_input_token_budget", 12000),
            enforce_input_budget=optional_bool(runtime, "enforce_input_budget", True),
            raw_local_max_tokens=optional_int(raw_local, "max_tokens", 512),
            raw_local_temperature=float(raw_local.get("temperature", 0.7)),
            raw_local_top_p=float(raw_local.get("top_p", 0.9)),
            raw_local_stop=tuple(item for item in raw_local_stop if item),
            raw_local_extra_payload=dict(raw_local_extra),
            require_duplicate_soak_for_cloud_loop=optional_bool(
                safety,
                "require_duplicate_soak_for_cloud_loop",
                True,
            ),
            duplicate_soak_passed=optional_bool(safety, "duplicate_soak_passed", False),
        )
