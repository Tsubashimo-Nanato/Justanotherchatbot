from __future__ import annotations

from dataclasses import dataclass
from typing import Any


COMMAND_ALIASES = {
    ".enforce": "enforce",
    ".detail": "detail",
    ".debug": "debug",
    ".ignore": "ignore",
}
THINKING_LEVELS = {0, 1, 2, 3}


@dataclass(frozen=True)
class ParsedMessage:
    content: str
    enforced: bool
    debug_requested: bool
    diagnostic_requested: bool
    ignored: bool
    help_requested: bool
    status_requested: bool
    reboot_requested: bool
    set_requested: bool
    score_requested: bool
    score_value: float | None
    score_note: str
    thinking_level: int | None
    setting_updates: dict[str, Any]
    setting_errors: tuple[str, ...]
    command_suffixes: tuple[str, ...]

    @property
    def command_suffix(self) -> str:
        return " ".join(self.command_suffixes)


def parse_message_commands(message: str) -> ParsedMessage:
    text = message.strip()
    if not text:
        return _parsed_empty()

    standalone_text = _standalone_command_text(text)
    standalone_commands = {
        ".help": "help_requested",
        ".status": "status_requested",
        ".reboot": "reboot_requested",
        ".debug": "diagnostic_requested",
    }
    requested_flag = standalone_commands.get(standalone_text.casefold())
    if requested_flag is not None:
        return ParsedMessage(
            content="",
            enforced=False,
            debug_requested=False,
            diagnostic_requested=requested_flag == "diagnostic_requested",
            ignored=False,
            help_requested=requested_flag == "help_requested",
            status_requested=requested_flag == "status_requested",
            reboot_requested=requested_flag == "reboot_requested",
            set_requested=False,
            score_requested=False,
            score_value=None,
            score_note="",
            thinking_level=None,
            setting_updates={},
            setting_errors=(),
            command_suffixes=(standalone_text,),
        )

    if standalone_text.casefold().startswith(".set"):
        return _parse_set_command(standalone_text)

    if standalone_text.casefold().startswith(".score"):
        return _parse_score_command(standalone_text)

    tokens = text.split()
    suffixes: list[str] = []
    command_names: set[str] = set()
    thinking_level: int | None = None

    while tokens:
        token = tokens[-1].casefold()
        command = COMMAND_ALIASES.get(token)
        if command is not None:
            suffixes.append(tokens.pop())
            command_names.add(command)
            continue

        if _is_thinking_level_token(token) and len(tokens) >= 2 and tokens[-2].casefold() == ".think":
            level_token = tokens.pop()
            think_token = tokens.pop()
            thinking_level = int(level_token)
            suffixes.append(f"{think_token} {level_token}")
            continue

        if token == ".think":
            suffixes.append(tokens.pop())
            thinking_level = 1
            continue

        break

    content = " ".join(tokens).strip()
    suffixes.reverse()
    return ParsedMessage(
        content=content,
        enforced="enforce" in command_names,
        debug_requested="detail" in command_names,
        diagnostic_requested="debug" in command_names,
        ignored="ignore" in command_names,
        help_requested=False,
        status_requested=False,
        reboot_requested=False,
        set_requested=False,
        score_requested=False,
        score_value=None,
        score_note="",
        thinking_level=thinking_level,
        setting_updates={},
        setting_errors=(),
        command_suffixes=tuple(suffixes),
    )


def _parsed_empty() -> ParsedMessage:
    return ParsedMessage(
        content="",
        enforced=False,
        debug_requested=False,
        diagnostic_requested=False,
        ignored=False,
        help_requested=False,
        status_requested=False,
        reboot_requested=False,
        set_requested=False,
        score_requested=False,
        score_value=None,
        score_note="",
        thinking_level=None,
        setting_updates={},
        setting_errors=(),
        command_suffixes=(),
    )


def _standalone_command_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return text
    last_line = lines[-1]
    lowered = last_line.casefold()
    if lowered in {".help", ".status", ".reboot", ".debug"}:
        return last_line
    if lowered.startswith(".set") or lowered.startswith(".score"):
        return last_line
    return text


def _parse_set_command(text: str) -> ParsedMessage:
    tokens = text.split()
    if not tokens or tokens[0].casefold() != ".set":
        return _parsed_empty()

    updates: dict[str, Any] = {}
    errors: list[str] = []
    index = 1
    while index < len(tokens):
        key = tokens[index].casefold()
        if key == ".think":
            if index + 1 >= len(tokens):
                errors.append(".think requires 0, 1, 2, or 3")
                break
            value = tokens[index + 1]
            if not _is_thinking_level_token(value):
                errors.append(f".think must be 0, 1, 2, or 3, got {value}")
            else:
                updates["default_thinking_level"] = int(value)
            index += 2
            continue

        if key == ".activity":
            if index + 1 >= len(tokens):
                errors.append(".activity requires a number from 0 to 1")
                break
            value = tokens[index + 1]
            try:
                activity = float(value)
            except ValueError:
                errors.append(f".activity must be a number from 0 to 1, got {value}")
            else:
                if activity < 0 or activity > 1:
                    errors.append(f".activity must be from 0 to 1, got {value}")
                else:
                    updates["activity"] = activity
            index += 2
            continue

        errors.append(f"unsupported setting: {tokens[index]}")
        index += 1

    if not updates and not errors:
        errors.append(".set requires at least one setting")

    return ParsedMessage(
        content="",
        enforced=False,
        debug_requested=False,
        diagnostic_requested=False,
        ignored=False,
        help_requested=False,
        status_requested=False,
        reboot_requested=False,
        set_requested=True,
        score_requested=False,
        score_value=None,
        score_note="",
        thinking_level=None,
        setting_updates=updates,
        setting_errors=tuple(errors),
        command_suffixes=tuple(tokens),
    )


def _parse_score_command(text: str) -> ParsedMessage:
    parts = text.split(maxsplit=2)
    command = parts[0].casefold()
    value_text = ""
    note = ""
    if command == ".score":
        if len(parts) >= 2:
            value_text = parts[1]
        if len(parts) >= 3:
            note = parts[2].strip()
    else:
        value_text = command.removeprefix(".score")
        if len(parts) >= 2:
            note = " ".join(parts[1:]).strip()

    errors: list[str] = []
    score_value: float | None = None
    try:
        score_value = float(value_text)
    except ValueError:
        errors.append(".score requires a number from 0 to 1")
    else:
        if score_value < 0 or score_value > 1:
            errors.append(f".score must be from 0 to 1, got {value_text}")

    return ParsedMessage(
        content="",
        enforced=False,
        debug_requested=False,
        diagnostic_requested=False,
        ignored=False,
        help_requested=False,
        status_requested=False,
        reboot_requested=False,
        set_requested=False,
        score_requested=True,
        score_value=score_value,
        score_note=note,
        thinking_level=None,
        setting_updates={},
        setting_errors=tuple(errors),
        command_suffixes=tuple(text.split()),
    )


def _is_thinking_level_token(token: str) -> bool:
    try:
        level = int(token)
    except ValueError:
        return False
    return level in THINKING_LEVELS
