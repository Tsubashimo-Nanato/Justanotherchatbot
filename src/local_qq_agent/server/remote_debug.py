from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from typing import Any, TextIO

from local_qq_agent.paths import ensure_parent


PUBLIC_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")


@dataclass(frozen=True)
class RemoteDebugCredentials:
    username: str
    password: str

    def to_dict(self) -> dict[str, str]:
        return {
            "username": self.username,
            "password": self.password,
        }


class RemoteDebugManager:
    def __init__(self, *, project_root: Path, debug_port: int) -> None:
        self.project_root = project_root
        self.debug_port = debug_port
        self.runtime_dir = project_root / "artifacts" / "runtime"
        self.proxy_process: subprocess.Popen[str] | None = None
        self.tunnel_process: subprocess.Popen[str] | None = None
        self._log_handles: list[TextIO] = []
        self._credentials: RemoteDebugCredentials | None = None
        self._public_url = ""
        self._local_proxy_url = ""
        self._error = ""

    def status(self) -> dict[str, Any]:
        payload = self._persisted_status()
        payload.update(
            {
                "running": self._process_running(self.proxy_process) and self._process_running(self.tunnel_process),
                "proxy_running": self._process_running(self.proxy_process),
                "tunnel_running": self._process_running(self.tunnel_process),
                "proxy_pid": self.proxy_process.pid if self.proxy_process else None,
                "tunnel_pid": self.tunnel_process.pid if self.tunnel_process else None,
                "public_url": self._public_url or payload.get("public_url", ""),
                "local_proxy_url": self._local_proxy_url or payload.get("local_proxy_url", ""),
                "username": self._credentials.username if self._credentials else payload.get("username", ""),
                "password": self._credentials.password if self._credentials else payload.get("password", ""),
                "target_url": f"http://127.0.0.1:{self.debug_port}",
                "error": self._error,
                "credentials_path": str(self.credentials_path),
                "public_path": str(self.public_status_path),
                "cloudflared": self._cloudflared_path() or "",
            }
        )
        return payload

    def start(self) -> dict[str, Any]:
        if self._process_running(self.proxy_process) and self._process_running(self.tunnel_process):
            return self.status()

        self.stop()
        ensure_parent(self.credentials_path)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._error = ""
        self._public_url = ""
        self._credentials = RemoteDebugCredentials(
            username="debug",
            password=secrets.token_urlsafe(18),
        )
        proxy_port = self._find_free_port(start=18765)
        self._local_proxy_url = f"http://127.0.0.1:{proxy_port}"

        cloudflared = self._cloudflared_path()
        if not cloudflared:
            self._error = "cloudflared_not_found"
            self._write_public_status()
            return self.status()

        self._start_proxy(proxy_port)
        if not self._process_running(self.proxy_process):
            self._error = "remote_debug_proxy_failed_to_start"
            self._write_public_status()
            return self.status()

        self._start_cloudflared(cloudflared)
        self._public_url = self._wait_for_public_url(timeout_seconds=30.0)
        if not self._public_url:
            self._error = "cloudflared_public_url_not_found"

        self._write_credentials()
        self._write_public_status()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._terminate(self.tunnel_process)
        self._terminate(self.proxy_process)
        self.tunnel_process = None
        self.proxy_process = None
        self._close_logs()
        self._write_public_status()
        return self.status()

    @property
    def credentials_path(self) -> Path:
        return self.runtime_dir / "remote_debug_credentials.json"

    @property
    def public_status_path(self) -> Path:
        return self.runtime_dir / "remote_debug_public.json"

    def _start_proxy(self, proxy_port: int) -> None:
        assert self._credentials is not None
        proxy_script = self.project_root / "scripts" / "remote_debug_proxy.py"
        stdout = self._open_log("remote_debug_proxy.out.log")
        stderr = self._open_log("remote_debug_proxy.err.log")
        self.proxy_process = subprocess.Popen(
            [
                sys.executable,
                str(proxy_script),
                "--host",
                "127.0.0.1",
                "--port",
                str(proxy_port),
                "--target",
                f"http://127.0.0.1:{self.debug_port}",
                "--user",
                self._credentials.username,
                "--password",
                self._credentials.password,
            ],
            cwd=self.project_root,
            stdout=stdout,
            stderr=stderr,
            text=True,
            creationflags=self._creation_flags(),
        )
        time.sleep(0.5)

    def _start_cloudflared(self, executable: str) -> None:
        stdout = self._open_log("cloudflared.out.log")
        stderr = self._open_log("cloudflared.err.log")
        self.tunnel_process = subprocess.Popen(
            [
                executable,
                "tunnel",
                "--url",
                self._local_proxy_url,
                "--no-autoupdate",
            ],
            cwd=self.project_root,
            stdout=stdout,
            stderr=stderr,
            text=True,
            creationflags=self._creation_flags(),
        )

    def _cloudflared_path(self) -> str:
        candidates = [
            self.project_root / "artifacts" / "runtime" / "cloudflared.exe",
            Path("E:/Mess/Projects/Programming/Chatbot/artifacts/runtime/cloudflared.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return shutil.which("cloudflared") or shutil.which("cloudflared.exe") or ""

    def _wait_for_public_url(self, *, timeout_seconds: float) -> str:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not self._process_running(self.tunnel_process):
                break
            for path in (self.runtime_dir / "cloudflared.out.log", self.runtime_dir / "cloudflared.err.log"):
                text = self._read_tail(path, max_chars=12000)
                match = PUBLIC_URL_PATTERN.search(text)
                if match:
                    return match.group(0)
            time.sleep(0.5)
        return ""

    def _write_credentials(self) -> None:
        if not self._credentials:
            return
        self.credentials_path.write_text(
            json.dumps(self._credentials.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_public_status(self) -> None:
        ensure_parent(self.public_status_path)
        payload = {
            "public_url": self._public_url,
            "local_proxy_url": self._local_proxy_url,
            "username": self._credentials.username if self._credentials else "",
            "password": self._credentials.password if self._credentials else "",
            "error": self._error,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        self.public_status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _persisted_status(self) -> dict[str, Any]:
        if not self.public_status_path.exists():
            return {}
        try:
            decoded = json.loads(self.public_status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    def _open_log(self, name: str) -> TextIO:
        path = self.runtime_dir / name
        ensure_parent(path)
        handle = path.open("a", encoding="utf-8")
        self._log_handles.append(handle)
        return handle

    def _close_logs(self) -> None:
        for handle in self._log_handles:
            try:
                handle.close()
            except OSError:
                pass
        self._log_handles = []

    def _terminate(self, process: subprocess.Popen[str] | None) -> None:
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _find_free_port(self, *, start: int) -> int:
        for port in range(start, start + 100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError:
                    continue
                return port
        raise RuntimeError("no free local proxy port found")

    def _process_running(self, process: subprocess.Popen[str] | None) -> bool:
        return process is not None and process.poll() is None

    def _read_tail(self, path: Path, *, max_chars: int) -> str:
        if not path.exists():
            return ""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return text[-max_chars:]

    def _creation_flags(self) -> int:
        if os.name != "nt":
            return 0
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
