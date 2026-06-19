from __future__ import annotations

from pathlib import Path

from local_qq_agent.paths import ensure_parent, project_path


ENV_PATH = project_path(".env")


def read_env_file(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _unquote(value.strip())
    return values


def save_env_value(key: str, value: str, path: Path = ENV_PATH) -> None:
    key = key.strip()
    if not key:
        raise ValueError("env key must not be empty")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    output: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        existing_key, _existing_value = stripped.split("=", 1)
        if existing_key.strip() != key:
            output.append(line)
            continue
        output.append(f"{key}={_quote(value)}")
        replaced = True

    if not replaced:
        output.append(f"{key}={_quote(value)}")

    ensure_parent(path)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def masked_secret(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"...{value[-4:]}"


def _quote(value: str) -> str:
    if not value or any(char.isspace() for char in value) or "#" in value:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value
