from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

import httpx
import yaml

from local_qq_agent.config import ConfigError, ModelConfig, read_yaml
from local_qq_agent.paths import ensure_parent, project_path


@dataclass(frozen=True)
class ModelProfile:
    name: str
    model: str
    repo_id: str
    filename: str
    target_path: Path
    context_tokens_target: int
    exists: bool
    size_bytes: int
    server: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_path"] = str(self.target_path)
        return payload


def model_profiles(path: str | Path = "config/model.yaml") -> dict[str, Any]:
    raw = read_yaml(path)
    active = str(raw.get("active_profile", "")).strip()
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        config = ModelConfig.load(path)
        active = config.active_profile
        entries = {active: _profile_from_config(active, config).to_dict()}
    else:
        entries = {}
        for name in profiles:
            config = ModelConfig.load_for_profile(name, path)
            entries[name] = _profile_from_config(name, config).to_dict()

    return {"active_profile": active, "profiles": entries}


def set_active_model_profile(profile_name: str, path: str | Path = "config/model.yaml") -> ModelConfig:
    profile_name = profile_name.strip()
    if not profile_name:
        raise ConfigError("profile_name must not be empty")

    resolved = project_path(path)
    raw = read_yaml(resolved)
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict) or profile_name not in profiles:
        raise ConfigError(f"unknown model profile: {profile_name}")

    raw["active_profile"] = profile_name
    resolved.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ModelConfig.load(resolved)


def download_model(config: ModelConfig) -> dict[str, Any]:
    from huggingface_hub import hf_hub_download

    target = config.download_target_path
    ensure_parent(target)
    if target.exists() and target.stat().st_size > 0:
        return {
            "downloaded": False,
            "reason": "already_exists",
            "target_path": str(target),
            "size_bytes": target.stat().st_size,
        }

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    downloaded = hf_hub_download(
        repo_id=config.download_repo_id,
        filename=config.download_filename,
        local_dir=str(target.parent),
        token=token,
    )
    if downloaded != str(target):
        shutil.copyfile(downloaded, target)

    return {
        "downloaded": True,
        "reason": "downloaded",
        "target_path": str(target),
        "size_bytes": target.stat().st_size,
    }


def restart_llama_server(config: ModelConfig, *, wait_seconds: int = 180) -> dict[str, Any]:
    stop_result = stop_port_listener(config.server_port)
    start_result = start_llama_server(config)
    ready = wait_for_model_server(config, seconds=wait_seconds)
    return {"stopped": stop_result, "started": start_result, "ready": ready}


def stop_port_listener(port: int) -> dict[str, Any]:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        return {"ok": False, "reason": "powershell_not_found"}

    script = f"""
$connections = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue
$stopped = @()
foreach ($connection in $connections) {{
    Stop-Process -Id $connection.OwningProcess -Force
    $stopped += $connection.OwningProcess
}}
$stopped | ConvertTo-Json -Compress
"""
    completed = subprocess.run(
        [powershell, "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        return {"ok": False, "reason": completed.stderr.strip() or "stop_failed"}

    return {"ok": True, "port": port, "stopped": completed.stdout.strip() or "[]"}


def start_llama_server(config: ModelConfig) -> dict[str, Any]:
    python = project_path(".venv/Scripts/python.exe")
    if not python.exists():
        python = Path(shutil.which("python") or "python")

    runtime_dir = project_path("artifacts/runtime")
    ensure_parent(runtime_dir / "llama.out.log")
    out_log = runtime_dir / "llama.out.log"
    err_log = runtime_dir / "llama.err.log"
    env = os.environ.copy()
    env["PATH"] = _cuda_path_prefix() + env.get("PATH", "")

    command = build_llama_server_command(config, python=python)

    with out_log.open("ab") as stdout, err_log.open("ab") as stderr:
        process = subprocess.Popen(
            command["args"],
            cwd=str(project_path(".")),
            stdout=stdout,
            stderr=stderr,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    return {
        "ok": True,
        "pid": process.pid,
        "model": config.model,
        "profile": config.active_profile,
        "target_path": str(config.download_target_path),
        "base_url": config.base_url,
        "server": _server_config(config),
        "args": command["args"],
        "skipped_args": command["skipped_args"],
    }


def wait_for_model_server(config: ModelConfig, *, seconds: int) -> dict[str, Any]:
    deadline = time.time() + seconds
    last_error = ""
    while time.time() < deadline:
        try:
            response = httpx.get(f"{config.base_url}/models", timeout=3)
            if 200 <= response.status_code < 300:
                return {"ok": True, "status_code": response.status_code, "base_url": config.base_url}
            last_error = f"status_code={response.status_code}"
        except httpx.HTTPError as error:
            last_error = str(error)
        time.sleep(1)

    return {"ok": False, "reason": "model_server_not_ready", "error": last_error, "base_url": config.base_url}


def _profile_from_config(name: str, config: ModelConfig) -> ModelProfile:
    target = config.download_target_path
    size = target.stat().st_size if target.exists() else 0
    return ModelProfile(
        name=name,
        model=config.model,
        repo_id=config.download_repo_id,
        filename=config.download_filename,
        target_path=target,
        context_tokens_target=config.context_tokens_target,
        exists=target.exists(),
        size_bytes=size,
        server=_server_config(config),
    )


def build_llama_server_command(config: ModelConfig, *, python: Path | None = None) -> dict[str, Any]:
    if python is None:
        python = project_path(".venv/Scripts/python.exe")
        if not python.exists():
            python = Path(shutil.which("python") or "python")

    pairs: list[tuple[str, str]] = [
        ("--model", str(config.download_target_path)),
        ("--host", config.server_host),
        ("--port", str(config.server_port)),
        ("--n_ctx", str(config.server_n_ctx)),
        ("--n_gpu_layers", str(config.server_n_gpu_layers)),
        ("--n_batch", str(config.server_n_batch)),
    ]
    if config.server_n_threads is not None:
        pairs.append(("--n_threads", str(config.server_n_threads)))
    if config.server_n_threads_batch is not None:
        pairs.append(("--n_threads_batch", str(config.server_n_threads_batch)))

    args = [str(python), "-m", "llama_cpp.server"]
    skipped_args: list[str] = []
    supported_args = llama_server_supported_args()
    for key, value in pairs:
        if supported_args and key not in supported_args:
            skipped_args.extend([key, value])
            continue
        args.extend([key, value])

    extra_args = list(config.server_extra_args)
    args.extend(extra_args)
    return {"args": args, "skipped_args": skipped_args, "extra_args": extra_args}


@lru_cache(maxsize=1)
def llama_server_supported_args() -> set[str]:
    python = project_path(".venv/Scripts/python.exe")
    if not python.exists():
        python = Path(shutil.which("python") or "python")

    env = os.environ.copy()
    env["PATH"] = _cuda_path_prefix() + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(
            [str(python), "-m", "llama_cpp.server", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    output = f"{completed.stdout}\n{completed.stderr}"
    if not output.strip():
        return set()

    return {
        token.strip(" ,")
        for token in output.split()
        if token.startswith("--")
    }


def _server_config(config: ModelConfig) -> dict[str, Any]:
    return {
        "host": config.server_host,
        "port": config.server_port,
        "n_ctx": config.server_n_ctx,
        "n_gpu_layers": config.server_n_gpu_layers,
        "n_batch": config.server_n_batch,
        "threads": config.server_n_threads,
        "threads_batch": config.server_n_threads_batch,
        "extra_args": list(config.server_extra_args),
    }


def _cuda_path_prefix() -> str:
    site_packages = project_path(".venv/Lib/site-packages")
    paths = [
        site_packages / "nvidia/cuda_runtime/bin",
        site_packages / "nvidia/cublas/bin",
        site_packages / "nvidia/cuda_nvrtc/bin",
    ]
    existing = [str(path) for path in paths if path.exists()]
    if not existing:
        return ""
    return ";".join(existing) + ";"
