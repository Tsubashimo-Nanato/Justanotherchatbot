from local_qq_agent.provider.env_file import masked_secret
from local_qq_agent.provider.grok_client import GrokClient, estimate_input_tokens, trim_text_middle
from local_qq_agent.provider.runtime import UnloadedModelClient
from local_qq_agent.provider.tracing import ProviderTraceStore
from local_qq_agent.provider.usage import ProviderUsageLedger
from local_qq_agent.memory import SQLiteMemoryStore


def test_masked_secret_never_returns_full_value():
    assert masked_secret("") == ""
    assert masked_secret("short") == "***"
    assert masked_secret("xai-1234567890") == "...7890"


def test_unloaded_client_blocks_chat():
    import asyncio

    client = UnloadedModelClient()
    health = asyncio.run(client.health())

    assert health["ok"] is False
    assert health["provider"] == "unloaded"
    try:
        asyncio.run(client.chat([{"role": "user", "content": "hi"}]))
    except RuntimeError as error:
        assert "unloaded" in str(error)
    else:
        raise AssertionError("unloaded provider should not chat")


def test_provider_config_runtime_input_budget_loaded():
    from local_qq_agent.config import ProviderConfig

    config = ProviderConfig.load()

    assert config.active_provider in {"unloaded", "local", "grok", "hybrid", "grok_responses", "hybrid_responses"}
    assert config.per_message_input_token_budget >= 4000
    assert config.enforce_input_budget is True
    assert config.grok_reasoning_simple_chat == "none"
    assert config.grok_reasoning_final_reply in {"low", "medium", "high"}
    assert config.grok_reasoning_web_fact in {"medium", "high"}
    assert config.grok_cache_enabled is True


def test_grok_payload_uses_operation_reasoning_and_cache_header(tmp_path):
    from local_qq_agent.config import ModelConfig, ProviderConfig

    provider_config = ProviderConfig.load()
    model_config = ModelConfig.load()
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    client = GrokClient(
        provider_config=provider_config,
        model_config=model_config,
        api_key="xai-test-key",
        traces=ProviderTraceStore(),
        usage=ProviderUsageLedger(store, budget=1000, degrade_at_ratio=0.8),
    )

    simple_payload = client._base_payload([{"role": "user", "content": "hi"}], max_tokens=8, operation="simple_chat")
    web_payload = client._responses_payload([{"role": "user", "content": "weather"}], max_tokens=8, operation="web_fact")
    chat_headers = client._headers(chat_cache=True)
    response_headers = client._headers()

    assert simple_payload["reasoning_effort"] == provider_config.grok_reasoning_simple_chat
    assert web_payload["reasoning"]["effort"] == provider_config.grok_reasoning_web_fact
    assert web_payload["prompt_cache_key"].startswith("qq-agent-")
    assert chat_headers["x-grok-conv-id"].startswith("qq-agent-")
    assert "x-grok-conv-id" not in response_headers


def test_usage_ledger_records_cached_reasoning_and_cost_ticks(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    usage = ProviderUsageLedger(store, budget=1000, degrade_at_ratio=0.8)
    usage.record(
        provider="grok",
        model="grok-4.3",
        operation="final_reply",
        trace_id="trace-1",
        usage={
            "prompt_tokens": 100,
            "completion_tokens": 12,
            "total_tokens": 112,
            "prompt_tokens_details": {"cached_tokens": 80},
            "completion_tokens_details": {"reasoning_tokens": 3},
            "cost_in_usd_ticks": 250,
            "num_sources_used": 2,
            "num_server_side_tools_used": 1,
        },
    )

    snapshot = usage.snapshot().to_dict()

    assert snapshot["prompt_tokens"] == 100
    assert snapshot["completion_tokens"] == 12
    assert snapshot["cached_tokens"] == 80
    assert snapshot["reasoning_tokens"] == 3
    assert snapshot["cost_in_usd_ticks"] == 250
    assert snapshot["source_count"] == 2
    assert snapshot["tool_count"] == 1


def test_input_budget_trim_preserves_edges():
    text = "A" * 2000 + "middle" * 2000 + "Z" * 2000
    trimmed = trim_text_middle(text, target_tokens=900)

    assert "[trimmed by per-message input budget]" in trimmed
    assert trimmed.startswith("A")
    assert trimmed.endswith("Z")
    assert estimate_input_tokens([{"role": "user", "content": trimmed}]) < estimate_input_tokens(
        [{"role": "user", "content": text}]
    )
