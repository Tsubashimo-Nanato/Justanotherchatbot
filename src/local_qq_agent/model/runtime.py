from __future__ import annotations

import json
import platform
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse

from local_qq_agent.config import ModelConfig


def collect_model_runtime(config: ModelConfig) -> dict[str, Any]:
    return {
        "configured": {
            "base_url": config.base_url,
            "model": config.model,
            "context_tokens_target": config.context_tokens_target,
            "context_tokens_fallback": config.context_tokens_fallback,
            "max_tokens": config.max_tokens,
            "timeout_seconds": config.timeout_seconds,
            "server": {
                "n_ctx": config.server_n_ctx,
                "n_gpu_layers": config.server_n_gpu_layers,
                "n_batch": config.server_n_batch,
                "threads": config.server_n_threads,
                "threads_batch": config.server_n_threads_batch,
                "extra_args": list(config.server_extra_args),
            },
        },
        "process": model_server_process(config.base_url),
        "gpu": nvidia_smi_snapshot(),
    }


def model_server_process(base_url: str) -> dict[str, Any]:
    port = _port_from_url(base_url)
    if port is None:
        return {"ok": False, "reason": f"base_url has no port: {base_url}"}

    if platform.system() != "Windows":
        return {"ok": False, "reason": "model process lookup is implemented for Windows in this demo."}

    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        return {"ok": False, "reason": "PowerShell was not found."}

    script = f"""
    $connection = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $connection) {{ return }}
    $owner = $connection.OwningProcess
    $process = Get-Process -Id $owner -ErrorAction SilentlyContinue
    if ($null -eq $process) {{ return }}
    [PSCustomObject]@{{
        ok = $true
        port = {port}
        pid = $owner
        process_name = $process.ProcessName
        working_set_mb = [Math]::Round($process.WorkingSet64 / 1MB, 1)
        private_memory_mb = [Math]::Round($process.PrivateMemorySize64 / 1MB, 1)
        cpu_seconds = [Math]::Round($process.CPU, 1)
        start_time = $process.StartTime.ToString("o")
    }} | ConvertTo-Json -Compress
    """
    completed = _run_command([powershell, "-NoProfile", "-Command", script], timeout_seconds=5)
    if completed["returncode"] != 0:
        return {"ok": False, "reason": completed["stderr"] or "process lookup failed"}

    output = completed["stdout"].strip()
    if not output:
        return {"ok": False, "reason": f"no listener found on port {port}", "port": port}

    try:
        decoded = json.loads(output)
    except json.JSONDecodeError:
        return {"ok": False, "reason": "process lookup returned invalid JSON", "raw": output}

    if isinstance(decoded, dict):
        return decoded
    return {"ok": False, "reason": "process lookup returned an unexpected payload"}


def nvidia_smi_snapshot() -> dict[str, Any]:
    command = shutil.which("nvidia-smi")
    if command is None:
        return {"ok": False, "reason": "nvidia-smi was not found."}

    completed = _run_command(
        [
            command,
            "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout_seconds=5,
    )
    if completed["returncode"] != 0:
        return {"ok": False, "reason": completed["stderr"] or "nvidia-smi failed"}

    gpus = [_parse_gpu_line(line) for line in completed["stdout"].splitlines() if line.strip()]
    return {"ok": True, "gpus": [gpu for gpu in gpus if gpu is not None]}


def _run_command(command: list[str], *, timeout_seconds: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"returncode": 1, "stdout": "", "stderr": str(error)}

    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr.strip(),
    }


def _parse_gpu_line(line: str) -> dict[str, Any] | None:
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 6:
        return None

    return {
        "name": parts[0],
        "memory_total_mb": _int_or_none(parts[1]),
        "memory_used_mb": _int_or_none(parts[2]),
        "memory_free_mb": _int_or_none(parts[3]),
        "utilization_percent": _int_or_none(parts[4]),
        "temperature_c": _int_or_none(parts[5]),
    }


def _port_from_url(url: str) -> int | None:
    try:
        return urlparse(url).port
    except ValueError:
        return None


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
