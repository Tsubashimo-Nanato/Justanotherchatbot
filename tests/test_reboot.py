from __future__ import annotations

import base64
import subprocess

from local_qq_agent.server.reboot import AgentRebooter


def test_rebooter_script_uses_literal_process_tools_path() -> None:
    script = AgentRebooter(port=8765, delay_seconds=0)._script(
        root=r"E:\project",
        python=r"E:\project\.venv\Scripts\python.exe",
        uvicorn_out=r"E:\project\artifacts\runtime\uvicorn.out.log",
        uvicorn_err=r"E:\project\artifacts\runtime\uvicorn.err.log",
        reboot_log=r"E:\project\artifacts\runtime\agent_reboot.log",
        process_tools=r"E:\project\scripts\runtime_processes.ps1",
        reason="test",
        current_process_id=1234,
    )

    assert "$ProcessTools = 'E:\\project\\scripts\\runtime_processes.ps1'" in script
    assert '"scripts\\runtime_processes.ps1"' not in script
    assert "$CurrentProcessId = 1234" in script
    assert "Stopping current FastAPI process " in script
    assert "Wait-PortReleased" in script
    assert "Port 8765 is still in use after restart cleanup" in script


def test_schedule_passes_current_pid_and_reboot_log(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_popen(args: list[str], **kwargs: object) -> object:
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = AgentRebooter(port=8765, delay_seconds=0).schedule(
        reason="unit_test",
        current_process_id=4321,
    )

    assert result["scheduled"] is True
    assert result["current_process_id"] == 4321
    assert result["port"] == 8765
    assert result["log_path"]
    assert calls

    args, kwargs = calls[0]
    assert args[:4] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW

    encoded = args[-1]
    script = base64.b64decode(encoded).decode("utf-16le")
    assert "$CurrentProcessId = 4321" in script
    assert "unit_test" in script
