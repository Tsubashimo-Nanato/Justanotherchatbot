from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import yaml

from local_qq_agent.config import ModelConfig, ProviderConfig
from local_qq_agent.memory import SQLiteMemoryStore
from local_qq_agent.model import OpenAICompatibleClient
from local_qq_agent.model.openai_client import ModelReply
from local_qq_agent.paths import ensure_parent, project_path
from local_qq_agent.provider.env_file import masked_secret, read_env_file, save_env_value
from local_qq_agent.provider.grok_client import GrokClient
from local_qq_agent.provider.tracing import ProviderTraceStore
from local_qq_agent.provider.usage import ProviderUsageLedger
from local_qq_agent.server.turn_ledger import TurnLedger


PROVIDER_CONFIG_PATH = project_path("config/provider.yaml")


class UnloadedModelClient:
    provider_name = "unloaded"
    supports_decision_call = False

    async def health(self) -> dict[str, Any]:
        return {
            "ok": False,
            "provider": self.provider_name,
            "reason": "provider_unloaded",
            "detail": "No model provider is loaded. Select local or Grok from the debug UI.",
        }

    async def chat(self, messages: list[dict[str, str]], *, max_tokens: int | None = None) -> ModelReply:
        raise RuntimeError("model provider is unloaded")

    def cloud_loop_preflight(self) -> dict[str, Any]:
        return {
            "ok": False,
            "reason": "provider_unloaded",
            "detail": "No model provider is loaded.",
        }


@dataclass(frozen=True)
class ProviderClientBundle:
    primary: Any
    gate: Any
    final: Any
    utility: Any
    mode: str


class ProviderRuntime:
    def __init__(self, *, store: SQLiteMemoryStore) -> None:
        self.store = store
        self.config = ProviderConfig.load()
        self.traces = ProviderTraceStore()
        self.usage = ProviderUsageLedger(
            store,
            budget=self.config.daily_token_budget,
            degrade_at_ratio=self.config.degrade_at_ratio,
        )

    def build_clients(self, model_config: ModelConfig) -> ProviderClientBundle:
        self.config = ProviderConfig.load()
        self.usage = ProviderUsageLedger(
            self.store,
            budget=self.config.daily_token_budget,
            degrade_at_ratio=self.config.degrade_at_ratio,
        )
        unloaded = UnloadedModelClient()
        local_client = OpenAICompatibleClient(model_config)
        grok_client = GrokClient(
            provider_config=self.config,
            model_config=model_config,
            api_key=self.api_key(),
            traces=self.traces,
            usage=self.usage,
        )
        if self.config.active_provider in {"local", "local_raw", "qwen"}:
            return ProviderClientBundle(
                primary=local_client,
                gate=local_client,
                final=local_client,
                utility=local_client,
                mode=self.config.active_provider,
            )
        if self.config.active_provider in {"grok", "grok_responses"}:
            return ProviderClientBundle(
                primary=grok_client,
                gate=grok_client,
                final=grok_client,
                utility=grok_client,
                mode="grok",
            )
        if self.config.active_provider in {"hybrid", "hybrid_responses"}:
            return ProviderClientBundle(
                primary=grok_client,
                gate=local_client,
                final=grok_client,
                utility=local_client,
                mode="hybrid",
            )
        return ProviderClientBundle(
            primary=unloaded,
            gate=unloaded,
            final=unloaded,
            utility=unloaded,
            mode="unloaded",
        )

    def build_client(self, model_config: ModelConfig):
        return self.build_clients(model_config).primary

    def api_key(self) -> str:
        return read_env_file().get("XAI_API_KEY", "")

    def save_api_key(self, api_key: str) -> dict[str, Any]:
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("api_key must not be empty")
        save_env_value("XAI_API_KEY", api_key)
        self.store.append_event(
            source="provider",
            kind="api_key_saved",
            content="XAI_API_KEY saved",
            metadata={"masked_key": masked_secret(api_key)},
        )
        return self.status()

    def switch_provider(self, provider: str) -> dict[str, Any]:
        provider = provider.strip().casefold()
        if provider not in {"unloaded", "local", "local_raw", "qwen", "grok", "hybrid", "grok_responses", "hybrid_responses"}:
            raise ValueError(f"unsupported provider: {provider}")
        data = _read_provider_yaml()
        data["active_provider"] = provider
        _write_provider_yaml(data)
        self.config = ProviderConfig.load()
        self.store.append_event(
            source="provider",
            kind="provider_switched",
            content=f"provider switched to {provider}",
            metadata={"provider": provider},
        )
        return self.status()

    def set_duplicate_soak_passed(self, passed: bool) -> dict[str, Any]:
        data = _read_provider_yaml()
        safety = data.setdefault("safety", {})
        if not isinstance(safety, dict):
            safety = {}
            data["safety"] = safety
        safety["duplicate_soak_passed"] = bool(passed)
        _write_provider_yaml(data)
        self.config = ProviderConfig.load()
        return self.status()

    def run_duplicate_soak(self) -> dict[str, Any]:
        ledger = TurnLedger(ttl_seconds=3600)
        first_id = "target|nanato revive"
        ledger.observe(
            turn_id=first_id,
            sender="target",
            clean_text="nanato revive",
            raw_text="nanato revive",
            fingerprint="fp-a",
            references_bot=False,
        )
        ledger.mark_queued(first_id)
        blocked_while_queued = not ledger.can_enqueue(first_id, "fp-b")
        ledger.mark_inflight(first_id)
        blocked_while_inflight = not ledger.can_enqueue(first_id, "fp-c")
        ledger.mark_completed(first_id)
        blocked_after_completed = not ledger.can_enqueue(first_id, "fp-d")
        ledger.observe(
            turn_id=first_id,
            sender="target",
            clean_text="nanato revive",
            raw_text="bot quote\nnanato revive",
            fingerprint="fp-e",
            references_bot=True,
        )
        blocked_after_alias = not ledger.can_enqueue(first_id, "fp-e")
        second_id = "target|different message"
        ledger.observe(
            turn_id=second_id,
            sender="target",
            clean_text="different message",
            raw_text="different message",
            fingerprint="fp-f",
            references_bot=False,
        )
        different_can_enqueue = ledger.can_enqueue(second_id, "fp-f")
        passed = all(
            [
                blocked_while_queued,
                blocked_while_inflight,
                blocked_after_completed,
                blocked_after_alias,
                different_can_enqueue,
            ]
        )
        self.set_duplicate_soak_passed(passed)
        result = {
            "ok": passed,
            "checks": {
                "blocked_while_queued": blocked_while_queued,
                "blocked_while_inflight": blocked_while_inflight,
                "blocked_after_completed": blocked_after_completed,
                "blocked_after_alias": blocked_after_alias,
                "different_can_enqueue": different_can_enqueue,
            },
            "ledger": ledger.summary(),
        }
        self.store.append_event(
            source="provider",
            kind="duplicate_soak_test",
            content="passed" if passed else "failed",
            metadata=result,
        )
        return result

    def cloud_loop_allowed(self) -> bool:
        if self.config.active_provider not in {"grok", "hybrid", "grok_responses", "hybrid_responses"}:
            return True
        if self.config.require_duplicate_soak_for_cloud_loop and not self.config.duplicate_soak_passed:
            return False
        return bool(self.api_key())

    def status(self) -> dict[str, Any]:
        key = self.api_key()
        usage = self.usage.snapshot()
        return {
            "active_provider": self.config.active_provider,
            "providers": ["unloaded", "local_raw", "qwen", "hybrid", "local", "grok", "grok_responses", "hybrid_responses"],
            "routing": self._routing_status(),
            "grok": {
                "model": self.config.grok_model,
                "base_url": self.config.grok_base_url,
                "api_key_configured": bool(key),
                "api_key_masked": masked_secret(key),
                "web_search_enabled": self.config.grok_enable_web_search,
                "endpoint": self.config.grok_endpoint,
                "reasoning": {
                    "simple_chat": self.config.grok_reasoning_simple_chat,
                    "final_reply": self.config.grok_reasoning_final_reply,
                    "rewrite": self.config.grok_reasoning_rewrite,
                    "web_fact": self.config.grok_reasoning_web_fact,
                    "complex_reasoning": self.config.grok_reasoning_complex_reasoning,
                },
                "cache": {
                    "enabled": self.config.grok_cache_enabled,
                    "scope": self.config.grok_cache_scope,
                },
            },
            "budget": usage.to_dict(),
            "runtime": {
                "per_message_input_token_budget": self.config.per_message_input_token_budget,
                "enforce_input_budget": self.config.enforce_input_budget,
                "daily_usage_is_telemetry_only": True,
            },
            "raw_local": self.raw_local_options(),
            "safety": {
                "require_duplicate_soak_for_cloud_loop": self.config.require_duplicate_soak_for_cloud_loop,
                "duplicate_soak_passed": self.config.duplicate_soak_passed,
                "cloud_loop_allowed": self.cloud_loop_allowed(),
            },
            "latest_trace": self.traces.latest(),
            "config": asdict(self.config),
        }

    def raw_local_enabled(self) -> bool:
        return self.config.active_provider == "local_raw"

    def qwen_first_enabled(self) -> bool:
        return self.config.active_provider == "qwen"

    def raw_local_options(self) -> dict[str, Any]:
        return {
            "enabled": self.raw_local_enabled(),
            "max_tokens": self.config.raw_local_max_tokens,
            "temperature": self.config.raw_local_temperature,
            "top_p": self.config.raw_local_top_p,
            "stop": list(self.config.raw_local_stop),
            "extra_payload": dict(self.config.raw_local_extra_payload),
            "instructions": "none",
            "context": "single user message only",
        }

    def _routing_status(self) -> dict[str, str]:
        if self.config.active_provider in {"hybrid", "hybrid_responses"}:
            return {"gate": "local", "final": "grok", "utility": "local"}
        if self.config.active_provider in {"grok", "grok_responses"}:
            return {"gate": "grok", "final": "grok", "utility": "grok"}
        if self.config.active_provider == "local_raw":
            return {"gate": "disabled", "final": "legacy_raw_qwen", "utility": "qwen"}
        if self.config.active_provider == "qwen":
            return {"gate": "qwen_first", "final": "qwen", "utility": "qwen"}
        if self.config.active_provider == "local":
            return {"gate": "legacy_local", "final": "legacy_local", "utility": "local"}
        return {"gate": "unloaded", "final": "unloaded", "utility": "unloaded"}


def _read_provider_yaml() -> dict[str, Any]:
    if not PROVIDER_CONFIG_PATH.exists():
        return {}
    with PROVIDER_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_provider_yaml(data: dict[str, Any]) -> None:
    ensure_parent(PROVIDER_CONFIG_PATH)
    with PROVIDER_CONFIG_PATH.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
