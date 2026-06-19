from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

import _bootstrap  # noqa: F401

from local_qq_agent.paths import ensure_parent, project_path


def run_command(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as error:
        return {"command": command, "error": str(error)}


def powershell_json(script: str) -> Any:
    result = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"{script} | ConvertTo-Json -Depth 5",
        ]
    )
    if result.get("returncode") != 0 or not result.get("stdout"):
        return result
    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError:
        return result


def is_admin() -> bool:
    script = (
        "([Security.Principal.WindowsPrincipal] "
        "[Security.Principal.WindowsIdentity]::GetCurrent())."
        "IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"
    )
    result = run_command(["powershell", "-NoProfile", "-Command", script])
    return result.get("stdout", "").strip().casefold() == "true"


def collect_report() -> dict[str, Any]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "is_admin": is_admin(),
        "cpu": powershell_json(
            "Get-CimInstance Win32_Processor | "
            "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,L2CacheSize,L3CacheSize"
        ),
        "memory": powershell_json(
            "Get-CimInstance Win32_PhysicalMemory | "
            "Select-Object Manufacturer,PartNumber,Capacity,Speed,ConfiguredClockSpeed,DeviceLocator"
        ),
        "computer": powershell_json(
            "Get-CimInstance Win32_ComputerSystem | "
            "Select-Object Manufacturer,Model,TotalPhysicalMemory"
        ),
        "os": powershell_json(
            "Get-CimInstance Win32_OperatingSystem | "
            "Select-Object Caption,Version,BuildNumber,OSArchitecture,FreePhysicalMemory"
        ),
        "disks": powershell_json(
            "Get-CimInstance Win32_LogicalDisk -Filter \"DriveType=3\" | "
            "Select-Object DeviceID,VolumeName,Size,FreeSpace,FileSystem"
        ),
        "gpu": run_command(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,memory.free,power.limit,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ]
        ),
        "docker": run_command(["docker", "--version"]),
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    gpu_stdout = report.get("gpu", {}).get("stdout", "")
    lines = [
        "# Hardware Diagnostics",
        "",
        f"- Administrator: {report.get('is_admin')}",
        f"- Platform: {report.get('platform')}",
        f"- GPU: {gpu_stdout or 'nvidia-smi unavailable'}",
        "",
        "## Model Fit",
        "",
        "- Target `Qwen3-14B-Q4_K_M` should be tested at 32k context first.",
        "- If GPU memory pressure or latency is poor, keep 14B and fall back to 16k context.",
        "- A future 3060 laptop target should keep the same architecture but may need 8B or lower context.",
        "",
        "## Notes",
        "",
        "- This script does not run a long pressure test.",
        "- Admin-only checks are skipped unless the terminal itself is elevated.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = collect_report()
    artifact_dir = project_path("artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    json_path = artifact_dir / "hardware_report.json"
    md_path = artifact_dir / "hardware_report.md"
    ensure_parent(json_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, md_path)

    print(f"Hardware report written: {json_path}")
    print(f"Hardware summary written: {md_path}")


if __name__ == "__main__":
    main()
