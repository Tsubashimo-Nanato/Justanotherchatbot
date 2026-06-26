from __future__ import annotations

from pathlib import Path


def test_agent_server_process_cleanup_only_targets_python_processes() -> None:
    script = Path("scripts/runtime_processes.ps1").read_text(encoding="utf-8")

    assert "ExecutablePath" in script
    assert "\\\\python(w)?\\.exe$" in script
    assert "$isPython -and $_.CommandLine -match" in script
    assert "local_qq_agent\\.server\\.app:create_app" in script
