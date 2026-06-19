from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import unicodedata


@dataclass(frozen=True)
class CleanTurn:
    original_text: str
    text: str
    removed_lines: tuple[str, ...]
    reason: str
    references_bot: bool = False

    def to_metadata(self) -> dict:
        return asdict(self)


STANDALONE_COMMANDS = (".help", ".status", ".reboot", ".debug")


def clean_turn_text(
    message: str,
    *,
    recent_bot_texts: tuple[str, ...] = (),
    quote_sender_names: tuple[str, ...] = (),
) -> CleanTurn:
    original = message.strip()
    if not original:
        return CleanTurn(original_text="", text="", removed_lines=(), reason="empty")

    lines = [line.strip() for line in original.splitlines() if line.strip()]
    if not lines:
        return CleanTurn(original_text=original, text="", removed_lines=(), reason="empty_lines")

    kept: list[str] = []
    removed: list[str] = []
    references_bot = False
    for index, line in enumerate(lines):
        before_latest = index < len(lines) - 1
        bot_sender_line = before_latest and _matches_quote_sender_name(line, quote_sender_names)
        recent_bot_line = before_latest and _matches_recent_bot_text(line, recent_bot_texts, allow_short=True)
        if bot_sender_line or recent_bot_line:
            references_bot = True

        if _is_noise_line(line) or bot_sender_line or recent_bot_line:
            removed.append(line)
            continue
        kept.append(line)

    if not kept:
        return CleanTurn(
            original_text=original,
            text="",
            removed_lines=tuple(removed),
            reason="all_noise",
            references_bot=references_bot,
        )

    standalone = _standalone_command_from_lines(kept)
    if standalone:
        removed.extend(line for line in kept if line != standalone)
        return CleanTurn(
            original_text=original,
            text=standalone,
            removed_lines=tuple(removed),
            reason="standalone_command_last_line",
            references_bot=references_bot,
        )

    if removed and len(kept) > 1:
        return CleanTurn(
            original_text=original,
            text=kept[-1],
            removed_lines=tuple(removed + kept[:-1]),
            reason="noise_removed_latest_line",
            references_bot=references_bot,
        )

    if _looks_like_quote_merge(kept):
        quote_lines = kept[:-1]
        return CleanTurn(
            original_text=original,
            text=kept[-1],
            removed_lines=tuple(quote_lines),
            reason="quote_merge_latest_line",
            references_bot=references_bot or _lines_reference_bot(quote_lines, recent_bot_texts, quote_sender_names),
        )

    return CleanTurn(
        original_text=original,
        text="\n".join(kept),
        removed_lines=tuple(removed),
        reason="unchanged",
        references_bot=references_bot,
    )


def _standalone_command_from_lines(lines: list[str]) -> str:
    for line in reversed(lines):
        lowered = line.casefold()
        if lowered in STANDALONE_COMMANDS:
            return line
        if lowered.startswith(".set") or lowered.startswith(".score"):
            return line
    return ""


def _looks_like_quote_merge(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    if len(lines[-1]) > 140:
        return False
    if any(_line_has_command(line) for line in lines[:-1]):
        return True
    if _looks_like_time_or_status(lines[0]):
        return True
    if len(lines) >= 3 and _looks_like_short_old_reply(lines[1]):
        return True
    return False


def _line_has_command(line: str) -> bool:
    lowered = line.casefold()
    return any(command in lowered for command in (".help", ".status", ".reboot", ".debug", ".set", ".score"))


def _looks_like_time_or_status(line: str) -> bool:
    if re.search(r"\d{1,2}\s*(?::|：|点)\s*\d{1,2}", line):
        return True
    return line.casefold().startswith(("status:", "commands:"))


def _looks_like_short_old_reply(line: str) -> bool:
    return len(line) <= 40 and bool(re.search(r"[。.!！?？…~～]$", line))


def _is_noise_line(line: str) -> bool:
    normalized = _compact(line)
    if "[debug" in normalized or "completion_tok_s=" in normalized or "prompt_tokens=" in normalized:
        return True
    if normalized in {"闪传文件", "发送文件", "图片", "视频"}:
        return True
    noise_fragments = (
        "支持超大文件",
        "单文件最大",
        "极速传输",
        "点击查看",
        "已发送文件",
    )
    return any(fragment in normalized for fragment in noise_fragments)


def _matches_recent_bot_text(line: str, recent_bot_texts: tuple[str, ...], *, allow_short: bool = False) -> bool:
    normalized = _compact(line)
    if len(normalized) < 2:
        return False
    for text in recent_bot_texts:
        compact = _compact(text)
        if not compact:
            continue
        if normalized == compact or normalized in compact or compact in normalized:
            return allow_short or len(normalized) >= 8
    return False


def _matches_quote_sender_name(line: str, quote_sender_names: tuple[str, ...]) -> bool:
    normalized = _compact(line)
    if not normalized:
        return False
    for name in quote_sender_names:
        compact_name = _compact(name)
        if not compact_name:
            continue
        if normalized == compact_name:
            return True
        if normalized.startswith(compact_name) and len(normalized) - len(compact_name) <= 8:
            return True
    return False


def _lines_reference_bot(
    lines: list[str],
    recent_bot_texts: tuple[str, ...],
    quote_sender_names: tuple[str, ...],
) -> bool:
    for line in lines:
        if _matches_quote_sender_name(line, quote_sender_names):
            return True
        if _matches_recent_bot_text(line, recent_bot_texts, allow_short=True):
            return True
    return False


def _compact(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = re.sub(r"\s+", "", normalized.casefold())
    return normalized.strip(" \t\r\n。.!！?？…~～，,：:；;、'\"“”‘’（）()[]【】")
