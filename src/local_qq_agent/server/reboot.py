from __future__ import annotations

import base64
from dataclasses import dataclass
import subprocess

from local_qq_agent.paths import ensure_parent, project_path


def _ps_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True)
class AgentRebooter:
    port: int = 8765
    host: str = "0.0.0.0"
    delay_seconds: int = 2

    def schedule(self, *, reason: str = "command") -> dict[str, str | int | bool]:
        root = project_path(".")
        runtime_dir = project_path("artifacts/runtime")
        ensure_parent(runtime_dir / "agent_reboot.log")

        python = root / ".venv/Scripts/python.exe"
        uvicorn_out = runtime_dir / "uvicorn.out.log"
        uvicorn_err = runtime_dir / "uvicorn.err.log"
        reboot_log = runtime_dir / "agent_reboot.log"

        command = f"""
$ErrorActionPreference = "Continue"
$Root = {_ps_string(str(root))}
$Python = {_ps_string(str(python))}
$OutLog = {_ps_string(str(uvicorn_out))}
$ErrLog = {_ps_string(str(uvicorn_err))}
$RebootLog = {_ps_string(str(reboot_log))}
$ProcessTools = Join-Path $Root "scripts\runtime_processes.ps1"
$Reason = {_ps_string(reason)}
function Write-RebootLog {{
    param([string]$Message)
    Add-Content -Path $RebootLog -Encoding UTF8 -Value ("[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] " + $Message)
}}
. $ProcessTools
Start-Sleep -Seconds {self.delay_seconds}
Write-RebootLog ("Restart requested: " + $Reason)
Stop-LocalAgentServers -LogAction ${{function:Write-RebootLog}}
Stop-LocalPortListeners -Ports @({self.port}) -LogAction ${{function:Write-RebootLog}}
Start-Sleep -Seconds 1
Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "local_qq_agent.server.app:create_app", "--factory", "--host", "{self.host}", "--port", "{self.port}") -WorkingDirectory $Root -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -WindowStyle Hidden
Write-RebootLog "Agent service start requested."
"""
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
        }
