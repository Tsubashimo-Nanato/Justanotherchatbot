from local_qq_agent.provider.env_file import masked_secret
from local_qq_agent.provider.grok_client import estimate_input_tokens, trim_text_middle
from local_qq_agent.provider.runtime import UnloadedModelClient


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

    assert config.active_provider in {"unloaded", "local", "grok", "hybrid"}
    assert config.per_message_input_token_budget >= 4000
    assert config.enforce_input_budget is True


def test_input_budget_trim_preserves_edges():
    text = "A" * 2000 + "middle" * 2000 + "Z" * 2000
    trimmed = trim_text_middle(text, target_tokens=900)

    assert "[trimmed by per-message input budget]" in trimmed
    assert trimmed.startswith("A")
    assert trimmed.endswith("Z")
    assert estimate_input_tokens([{"role": "user", "content": trimmed}]) < estimate_input_tokens(
        [{"role": "user", "content": text}]
    )
