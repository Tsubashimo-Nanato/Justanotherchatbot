from __future__ import annotations

import base64
from dataclasses import dataclass
import os
import subprocess

from local_qq_agent.paths import ensure_parent, project_path


def _ps_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True)
class AgentRebooter:
    port: int = 8765
    host: str = "0.0.0.0"
    delay_seconds: int = 2

    def schedule(
        self,
        *,
        reason: str = "command",
        current_process_id: int | None = None,
    ) -> dict[str, str | int | bool]:
        root = project_path(".")
        runtime_dir = project_path("artifacts/runtime")
        ensure_parent(runtime_dir / "agent_reboot.log")

        python = root / ".venv/Scripts/python.exe"
        uvicorn_out = runtime_dir / "uvicorn.out.log"
        uvicorn_err = runtime_dir / "uvicorn.err.log"
        reboot_log = runtime_dir / "agent_reboot.log"
        process_tools = root / "scripts" / "runtime_processes.ps1"
        process_id = current_process_id if current_process_id is not None else os.getpid()

        command = self._script(
            root=str(root),
            python=str(python),
            uvicorn_out=str(uvicorn_out),
            uvicorn_err=str(uvicorn_err),
            reboot_log=str(reboot_log),
            process_tools=str(process_tools),
            reason=reason,
            current_process_id=process_id,
        )
        encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            cwd=str(root),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return {
            "scheduled": True,
            "scope": "agent_only",
            "host": self.host,
            "port": self.port,
            "delay_seconds": self.delay_seconds,
            "reason": reason,
            "current_process_id": process_id,
            "log_path": str(reboot_log),
        }

    def _script(
        self,
        *,
        root: str,
        python: str,
        uvicorn_out: str,
        uvicorn_err: str,
        reboot_log: str,
        process_tools: str,
        reason: str,
        current_process_id: int,
    ) -> str:
        return f"""
$ErrorActionPreference = "Continue"
$Root = {_ps_string(root)}
$Python = {_ps_string(python)}
$OutLog = {_ps_string(uvicorn_out)}
$ErrLog = {_ps_string(uvicorn_err)}
$RebootLog = {_ps_string(reboot_log)}
$ProcessTools = {_ps_string(process_tools)}
$Reason = {_ps_string(reason)}
$CurrentProcessId = {current_process_id}
function Write-RebootLog {{
    param([string]$Message)
    Add-Content -Path $RebootLog -Encoding UTF8 -Value ("[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] " + $Message)
}}
. $ProcessTools
function Wait-PortReleased {{
    param(
        [int]$Port,
        [int]$Seconds
    )

    for ($i = 0; $i -lt $Seconds; $i++) {{
        $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        if ($listeners.Count -eq 0) {{
            return $true
        }}
        Start-Sleep -Seconds 1
    }}
    return $false
}}
Start-Sleep -Seconds {self.delay_seconds}
Write-RebootLog ("Restart requested: " + $Reason)
if ($CurrentProcessId -gt 0) {{
    Write-RebootLog ("Stopping current FastAPI process " + $CurrentProcessId + ".")
    Stop-Process -Id $CurrentProcessId -Force -ErrorAction SilentlyContinue
}}
Stop-LocalAgentServers -LogAction ${{function:Write-RebootLog}}
Stop-LocalPortListeners -Ports @({self.port}) -LogAction ${{function:Write-RebootLog}}
if (-not (Wait-PortReleased -Port {self.port} -Seconds 20)) {{
    Write-RebootLog "Port {self.port} is still in use after restart cleanup; aborting FastAPI start."
    exit 1
}}
Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "local_qq_agent.server.app:create_app", "--factory", "--host", "{self.host}", "--port", "{self.port}") -WorkingDirectory $Root -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -WindowStyle Hidden
Write-RebootLog "Agent service start requested."
"""
