from local_qq_agent.config import ModelConfig
from local_qq_agent.model.manager import build_llama_server_command, set_active_model_profile


def test_model_config_loads_active_profile(tmp_path):
    config_path = tmp_path / "model.yaml"
    config_path.write_text(
        """
active_profile: "large"
profiles:
  small:
    provider:
      base_url: "http://127.0.0.1:18080/v1"
      model: "small-model"
    generation:
      max_tokens: 96
      context_tokens_target: 4096
      context_tokens_fallback: 2048
    download:
      repo_id: "org/small"
      filename: "small.gguf"
      target_path: "models/small.gguf"
  large:
    provider:
      base_url: "http://127.0.0.1:18080/v1"
      model: "large-model"
      timeout_seconds: 150
    generation:
      max_tokens: 160
      context_tokens_target: 8192
      context_tokens_fallback: 4096
    download:
      repo_id: "org/large"
      filename: "large.gguf"
      target_path: "models/large.gguf"
    server:
      port: 18080
      n_ctx: 8192
      n_gpu_layers: -1
      n_batch: 512
""",
        encoding="utf-8",
    )

    config = ModelConfig.load(config_path)

    assert config.active_profile == "large"
    assert config.model == "large-model"
    assert config.download_filename == "large.gguf"
    assert config.server_n_gpu_layers == -1


def test_model_config_loads_server_offload_options(tmp_path):
    config_path = tmp_path / "model.yaml"
    config_path.write_text(
        """
active_profile: "hybrid"
profiles:
  hybrid:
    provider:
      base_url: "http://127.0.0.1:18080/v1"
      model: "hybrid-model"
    generation:
      max_tokens: 96
      context_tokens_target: 4096
      context_tokens_fallback: 2048
    download:
      repo_id: "org/hybrid"
      filename: "hybrid.gguf"
      target_path: "models/hybrid.gguf"
    server:
      n_ctx: 4096
      n_gpu_layers: 20
      n_batch: 256
      threads: 12
      threads_batch: 24
      extra_args:
        - "--flash_attn"
        - "true"
""",
        encoding="utf-8",
    )

    config = ModelConfig.load(config_path)

    assert config.server_n_gpu_layers == 20
    assert config.server_n_threads == 12
    assert config.server_n_threads_batch == 24
    assert config.server_extra_args == ("--flash_attn", "true")


def test_build_llama_server_command_includes_offload_options(monkeypatch, tmp_path):
    config_path = tmp_path / "model.yaml"
    config_path.write_text(
        """
active_profile: "cpu"
profiles:
  cpu:
    provider:
      base_url: "http://127.0.0.1:18080/v1"
      model: "cpu-model"
    generation:
      max_tokens: 96
      context_tokens_target: 4096
      context_tokens_fallback: 2048
    download:
      repo_id: "org/cpu"
      filename: "cpu.gguf"
      target_path: "models/cpu.gguf"
    server:
      n_ctx: 4096
      n_gpu_layers: 0
      n_batch: 256
      threads: 8
      threads_batch: 16
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "local_qq_agent.model.manager.llama_server_supported_args",
        lambda: {"--model", "--host", "--port", "--n_ctx", "--n_gpu_layers", "--n_batch", "--n_threads", "--n_threads_batch"},
    )

    config = ModelConfig.load(config_path)
    command = build_llama_server_command(config, python=tmp_path / "python.exe")

    args = command["args"]
    assert args[args.index("--n_gpu_layers") + 1] == "0"
    assert args[args.index("--n_threads") + 1] == "8"
    assert args[args.index("--n_threads_batch") + 1] == "16"
    assert command["skipped_args"] == []


def test_set_active_model_profile_updates_yaml(tmp_path):
    config_path = tmp_path / "model.yaml"
    config_path.write_text(
        """
active_profile: "small"
profiles:
  small:
    provider:
      base_url: "http://127.0.0.1:18080/v1"
      model: "small-model"
    generation:
      max_tokens: 96
      context_tokens_target: 4096
      context_tokens_fallback: 2048
    download:
      repo_id: "org/small"
      filename: "small.gguf"
      target_path: "models/small.gguf"
  large:
    provider:
      base_url: "http://127.0.0.1:18080/v1"
      model: "large-model"
    generation:
      max_tokens: 160
      context_tokens_target: 8192
      context_tokens_fallback: 4096
    download:
      repo_id: "org/large"
      filename: "large.gguf"
      target_path: "models/large.gguf"
""",
        encoding="utf-8",
    )

    config = set_active_model_profile("large", config_path)
    loaded = ModelConfig.load(config_path)

    assert config.active_profile == "large"
    assert loaded.active_profile == "large"
    assert loaded.model == "large-model"
