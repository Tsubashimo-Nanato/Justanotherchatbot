from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


COMMAND_ALIASES = {
    ".enforce": "enforce",
    ".detail": "detail",
    ".debug": "debug",
    ".ignore": "ignore",
}
COMMAND_TOKEN_ALIASES = {
    ".e": ".enforce",
    ".enforece": ".enforce",
    ".f": ".enforce",
    ".force": ".enforce",
    ".forced": ".enforce",
    ".d": ".debug",
    ".l": ".debug",
    ".log": ".debug",
    ".logs": ".debug",
    ".dbg": ".debug",
    ".details": ".detail",
}
KNOWN_COMMAND_TOKENS = {
    ".activity",
    ".debug",
    ".detail",
    ".enforce",
    ".help",
    ".ignore",
    ".loop",
    ".reboot",
    ".score",
    ".set",
    ".s",
    ".spon",
    ".spontaneous",
    ".status",
    ".think",
}
THINKING_LEVELS = {0, 1, 2, 3}


@dataclass(frozen=True)
class CommandResolution:
    text: str
    changed: bool = False
    source: str = "exact"
    replacements: tuple[tuple[str, str], ...] = ()
    unresolved_tokens: tuple[str, ...] = ()
    confidence: float = 1.0
    original_text: str = ""

    @property
    def notice(self) -> str:
        if not self.changed or not self.replacements:
            return ""
        original = _command_token_text(self.original_text or self.text)
        resolved = _command_token_text(self.text)
        if not original or not resolved:
            original = " ".join(original for original, _replacement in self.replacements)
            resolved = " ".join(replacement for _original, replacement in self.replacements)
        return f"Command resolved: {original} -> {resolved}"

    def to_metadata(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "source": self.source,
            "replacements": [{"from": original, "to": replacement} for original, replacement in self.replacements],
            "unresolved_tokens": list(self.unresolved_tokens),
            "confidence": self.confidence,
            "notice": self.notice,
        }


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
    loop_command: str
    spontaneous_requested: bool
    score_value: float | None
    score_note: str
    thinking_level: int | None
    setting_updates: dict[str, Any]
    setting_errors: tuple[str, ...]
    command_suffixes: tuple[str, ...]
    command_resolution_notice: str = ""
    command_resolution: dict[str, Any] = field(default_factory=dict)

    @property
    def command_suffix(self) -> str:
        return " ".join(self.command_suffixes)


def parse_message_commands(message: str, resolution: CommandResolution | None = None) -> ParsedMessage:
    resolution = resolution or resolve_command_aliases(message)
    message = resolution.text
    text = message.strip()
    if not text:
        return _parsed_empty(resolution)

    standalone_text = _standalone_command_text(text)
    loop_command = _loop_command(standalone_text)
    if loop_command:
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
            loop_command=loop_command,
            spontaneous_requested=False,
            score_value=None,
            score_note="",
            thinking_level=None,
            setting_updates={},
            setting_errors=(),
            command_suffixes=tuple(standalone_text.split()),
            command_resolution_notice=resolution.notice,
            command_resolution=resolution.to_metadata(),
        )

    if _spontaneous_command(standalone_text):
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
            loop_command="",
            spontaneous_requested=True,
            score_value=None,
            score_note="",
            thinking_level=None,
            setting_updates={},
            setting_errors=(),
            command_suffixes=(standalone_text,),
            command_resolution_notice=resolution.notice,
            command_resolution=resolution.to_metadata(),
        )

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
            loop_command="",
            spontaneous_requested=False,
            score_value=None,
            score_note="",
            thinking_level=None,
            setting_updates={},
            setting_errors=(),
            command_suffixes=(standalone_text,),
            command_resolution_notice=resolution.notice,
            command_resolution=resolution.to_metadata(),
        )

    if standalone_text.casefold().startswith(".set"):
        return _parse_set_command(standalone_text, resolution=resolution)

    if standalone_text.casefold().startswith(".score"):
        return _parse_score_command(standalone_text, resolution=resolution)

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
        loop_command="",
        spontaneous_requested=False,
        score_value=None,
        score_note="",
        thinking_level=thinking_level,
        setting_updates={},
        setting_errors=(),
        command_suffixes=tuple(suffixes),
        command_resolution_notice=resolution.notice,
        command_resolution=resolution.to_metadata(),
    )


def resolve_command_aliases(message: str) -> CommandResolution:
    tokens = re.findall(r"\S+", message)
    if not tokens:
        return CommandResolution(text=message)

    replacements: list[tuple[str, str]] = []
    resolved_text = message
    unresolved: list[str] = []
    for token in tokens:
        lowered = token.casefold()
        replacement = COMMAND_TOKEN_ALIASES.get(lowered)
        if replacement is not None:
            replacements.append((token, replacement))
            resolved_text = re.sub(rf"(?<!\S){re.escape(token)}(?!\S)", replacement, resolved_text)
            continue
        if _looks_like_unknown_command_token(token):
            unresolved.append(token)

    if not replacements and not unresolved:
        return CommandResolution(text=message)

    return CommandResolution(
        text=resolved_text,
        changed=bool(replacements),
        source="alias" if replacements else "exact",
        replacements=tuple(replacements),
        unresolved_tokens=tuple(unresolved),
        original_text=message,
    )


def resolution_from_model(
    *,
    original_text: str,
    replacements: dict[str, str],
    confidence: float,
) -> CommandResolution:
    tokens = re.findall(r"\S+", original_text)
    applied: list[tuple[str, str]] = []
    resolved_text = original_text
    allowed = KNOWN_COMMAND_TOKENS | set(COMMAND_ALIASES)
    for token in tokens:
        replacement = replacements.get(token) or replacements.get(token.casefold())
        if replacement is None:
            continue
        normalized = replacement.strip().casefold()
        if normalized not in allowed:
            continue
        applied.append((token, normalized))
        resolved_text = re.sub(rf"(?<!\S){re.escape(token)}(?!\S)", normalized, resolved_text)

    if not applied:
        return resolve_command_aliases(original_text)

    return CommandResolution(
        text=resolved_text,
        changed=True,
        source="local_model",
        replacements=tuple(applied),
        confidence=max(0.0, min(1.0, float(confidence))),
        original_text=original_text,
    )


def _parsed_empty(resolution: CommandResolution | None = None) -> ParsedMessage:
    resolution = resolution or CommandResolution(text="")
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
        loop_command="",
        spontaneous_requested=False,
        score_value=None,
        score_note="",
        thinking_level=None,
        setting_updates={},
        setting_errors=(),
        command_suffixes=(),
        command_resolution_notice=resolution.notice,
        command_resolution=resolution.to_metadata(),
    )


def _standalone_command_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return text
    last_line = lines[-1]
    lowered = last_line.casefold()
    if lowered in {".help", ".status", ".reboot", ".debug", ".s", ".spon", ".spontaneous"}:
        return last_line
    if lowered in {".loop start", ".loop stop"}:
        return last_line
    if lowered.startswith(".set") or lowered.startswith(".score"):
        return last_line
    return text


def _loop_command(text: str) -> str:
    tokens = text.strip().casefold().split()
    if len(tokens) != 2 or tokens[0] != ".loop":
        return ""
    if tokens[1] in {"start", "stop"}:
        return tokens[1]
    return ""


def _spontaneous_command(text: str) -> bool:
    return text.strip().casefold() in {".s", ".spon", ".spontaneous"}


def _parse_set_command(text: str, *, resolution: CommandResolution | None = None) -> ParsedMessage:
    resolution = resolution or CommandResolution(text=text)
    tokens = text.split()
    if not tokens or tokens[0].casefold() != ".set":
        return _parsed_empty(resolution)

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
        loop_command="",
        spontaneous_requested=False,
        score_value=None,
        score_note="",
        thinking_level=None,
        setting_updates=updates,
        setting_errors=tuple(errors),
        command_suffixes=tuple(tokens),
        command_resolution_notice=resolution.notice,
        command_resolution=resolution.to_metadata(),
    )


def _parse_score_command(text: str, *, resolution: CommandResolution | None = None) -> ParsedMessage:
    resolution = resolution or CommandResolution(text=text)
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
        loop_command="",
        spontaneous_requested=False,
        score_value=score_value,
        score_note=note,
        thinking_level=None,
        setting_updates={},
        setting_errors=tuple(errors),
        command_suffixes=tuple(text.split()),
        command_resolution_notice=resolution.notice,
        command_resolution=resolution.to_metadata(),
    )


def _is_thinking_level_token(token: str) -> bool:
    try:
        level = int(token)
    except ValueError:
        return False
    return level in THINKING_LEVELS


def _looks_like_unknown_command_token(token: str) -> bool:
    lowered = token.casefold()
    if not lowered.startswith("."):
        return False
    if lowered.startswith(".score") and lowered != ".score":
        return False
    if lowered in KNOWN_COMMAND_TOKENS or lowered in COMMAND_TOKEN_ALIASES:
        return False
    return lowered[1:].isalpha()


def _command_token_text(text: str) -> str:
    tokens = []
    for token in re.findall(r"\S+", text):
        if token.startswith("."):
            tokens.append(token)
    return " ".join(tokens)
