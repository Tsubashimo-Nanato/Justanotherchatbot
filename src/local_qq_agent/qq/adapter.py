from __future__ import annotations

from dataclasses import asdict, dataclass
import html
import platform
import re
import time
from typing import Any

from local_qq_agent.config import QQConfig


@dataclass(frozen=True)
class QQStatus:
    available: bool
    armed: bool
    dry_run: bool
    window_title_regex: str
    expected_group_name: str
    target_sender_name: str
    bot_sender_name: str
    active_group_name: str
    group_matched: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QQSendResult:
    sent: bool
    dry_run: bool
    reason: str
    text: str
    verification: dict[str, Any]
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QQChatMessage:
    sender_name: str
    text: str
    fingerprint: str
    rectangle: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QQReadResult:
    active_group_name: str
    expected_group_name: str
    target_sender_name: str
    bot_sender_name: str
    group_matched: bool
    visible_items: list[dict[str, Any]]
    chat_messages: list[QQChatMessage]
    target_messages: list[QQChatMessage]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QQWindowAdapter:
    def __init__(self, config: QQConfig) -> None:
        self.config = config
        self.armed = False

    def status(self) -> QQStatus:
        if platform.system() != "Windows":
            return QQStatus(
                available=False,
                armed=self.armed,
                dry_run=self.config.dry_run,
                window_title_regex=self.config.window_title_regex,
                expected_group_name=self.config.expected_group_name,
                target_sender_name=self.config.target_sender_name,
                bot_sender_name=self.config.bot_sender_name,
                active_group_name="",
                group_matched=False,
                detail="QQ window automation is only available on Windows.",
            )

        try:
            window = self._find_window()
        except Exception as error:
            return QQStatus(
                available=False,
                armed=self.armed,
                dry_run=self.config.dry_run,
                window_title_regex=self.config.window_title_regex,
                expected_group_name=self.config.expected_group_name,
                target_sender_name=self.config.target_sender_name,
                bot_sender_name=self.config.bot_sender_name,
                active_group_name="",
                group_matched=False,
                detail=str(error),
            )

        title = str(window.window_text())
        active_group_name = self._active_group_name(window)
        group_matched = self._group_matches(active_group_name)
        return QQStatus(
            available=True,
            armed=self.armed,
            dry_run=self.config.dry_run,
            window_title_regex=self.config.window_title_regex,
            expected_group_name=self.config.expected_group_name,
            target_sender_name=self.config.target_sender_name,
            bot_sender_name=self.config.bot_sender_name,
            active_group_name=active_group_name,
            group_matched=group_matched,
            detail=f"Found window: {title}",
        )

    def arm(self) -> QQStatus:
        self.armed = True
        return self.status()

    def disarm(self) -> QQStatus:
        self.armed = False
        return self.status()

    def probe(self) -> dict[str, Any]:
        window = self._find_window()
        entries: list[dict[str, Any]] = []
        self._collect_controls(window, depth=0, entries=entries)
        return {
            "window_title": str(window.window_text()),
            "active_group_name": self._active_group_name(window),
            "expected_group_name": self.config.expected_group_name,
            "target_sender_name": self.config.target_sender_name,
            "control_count": len(entries),
            "max_depth": self.config.probe_max_depth,
            "controls": entries,
        }

    def read_visible_context(self, *, passive: bool = False) -> QQReadResult:
        window = self._find_window()
        was_minimized = False if passive else self._prepare_window_for_interaction(window)
        try:
            if not passive:
                self._scroll_to_latest(window)
            return self._read_context_snapshot(window)
        finally:
            self._restore_minimized(window, was_minimized)

    def read_scrollback_context(self, *, pages: int = 3) -> QQReadResult:
        window = self._find_window()
        was_minimized = self._prepare_window_for_interaction(window)
        snapshots: list[QQReadResult] = []
        try:
            self._scroll_to_latest(window)
            snapshots.append(self._read_context_snapshot(window))
            for _ in range(max(0, min(int(pages), 8))):
                self._scroll_page_up(window)
                snapshots.append(self._read_context_snapshot(window))
            self._scroll_to_latest(window)
            return self._merge_read_results(snapshots)
        finally:
            self._restore_minimized(window, was_minimized)

    def send_text(self, text: str, *, reply_to: QQChatMessage | None = None) -> QQSendResult:
        started_at = time.perf_counter()
        text = text.strip()
        if not text:
            raise ValueError("QQ message text must not be empty")

        if self.config.send_requires_armed and not self.armed:
            return QQSendResult(
                sent=False,
                dry_run=self.config.dry_run,
                reason="not_armed",
                text=text,
                verification={},
                duration_seconds=round(time.perf_counter() - started_at, 3),
            )

        if self.config.dry_run:
            return QQSendResult(
                sent=False,
                dry_run=True,
                reason="dry_run",
                text=text,
                verification={"note": "QQ send was not executed because config/qq.yaml dry_run is true."},
                duration_seconds=round(time.perf_counter() - started_at, 3),
            )

        timings: dict[str, float] = {}
        step_started = time.perf_counter()
        window = self._find_window()
        timings["find_window_seconds"] = round(time.perf_counter() - step_started, 3)
        was_minimized = self._prepare_window_for_interaction(window)

        try:
            group_error = self._send_group_error(window)
            if group_error:
                return QQSendResult(
                    sent=False,
                    dry_run=False,
                    reason=str(group_error["reason"]),
                    text=text,
                    verification={**group_error, "timings": timings},
                    duration_seconds=round(time.perf_counter() - started_at, 3),
                )

            step_started = time.perf_counter()
            window.set_focus()
            timings["focus_seconds"] = round(time.perf_counter() - step_started, 3)

            if reply_to is not None:
                step_started = time.perf_counter()
                quote_result = self._open_quote_reply(window, reply_to)
                timings["quote_seconds"] = round(time.perf_counter() - step_started, 3)
                if not quote_result.get("ok"):
                    return QQSendResult(
                        sent=False,
                        dry_run=False,
                        reason="quote_failed",
                        text=text,
                        verification={**quote_result, "timings": timings},
                        duration_seconds=round(time.perf_counter() - started_at, 3),
                    )
                step_started = time.perf_counter()
                self._clear_quote_mention_prefix()
                timings["quote_cleanup_seconds"] = round(time.perf_counter() - step_started, 3)

            step_started = time.perf_counter()
            import pyperclip
            from pywinauto import keyboard

            pyperclip.copy(text)
            keyboard.send_keys("^v{ENTER}")
            timings["input_seconds"] = round(time.perf_counter() - step_started, 3)

            verification = {
                "mode": "quote_reply" if reply_to is not None else "sent_unverified",
                "quoted_message": reply_to.to_dict() if reply_to is not None else None,
            }
            if self.config.verify_after_send:
                verification["window_title"] = str(window.window_text())
            if reply_to is not None:
                verification["quote_cleanup"] = "backspace_twice"
            verification["timings"] = timings

            return QQSendResult(
                sent=True,
                dry_run=False,
                reason="sent",
                text=text,
                verification=verification,
                duration_seconds=round(time.perf_counter() - started_at, 3),
            )
        finally:
            self._restore_minimized(window, was_minimized)

    def _open_quote_reply(self, window: Any, reply_to: QQChatMessage) -> dict[str, Any]:
        points = self._quote_click_points(reply_to.rectangle)
        if not points:
            return {"ok": False, "reason": "missing_reply_rectangle", "message": reply_to.to_dict()}

        tried_points: list[dict[str, int]] = []
        try:
            from pywinauto import mouse

            clicked = False
            for point in points:
                tried_points.append({"x": point[0], "y": point[1]})
                mouse.click(button="right", coords=point)
                time.sleep(0.15)
                clicked = self._click_context_menu_item(("引用", "Quote", "Reply"))
                if clicked:
                    break
        except Exception as error:
            return {
                "ok": False,
                "reason": "quote_action_error",
                "error": str(error),
                "tried_click_points": tried_points,
                "message": reply_to.to_dict(),
            }

        if not clicked:
            return {
                "ok": False,
                "reason": "quote_menu_item_not_found",
                "tried_click_points": tried_points,
                "message": reply_to.to_dict(),
            }

        try:
            window.set_focus()
        except Exception:
            pass
        return {
            "ok": True,
            "reason": "quote_ready",
            "click_point": tried_points[-1],
            "tried_click_points": tried_points,
            "message": reply_to.to_dict(),
        }

    def _quote_click_point(self, rectangle: dict[str, int]) -> tuple[int, int] | None:
        points = self._quote_click_points(rectangle)
        if not points:
            return None
        return points[0]

    def _quote_click_points(self, rectangle: dict[str, int]) -> list[tuple[int, int]]:
        try:
            left = int(rectangle["left"])
            top = int(rectangle["top"])
            right = int(rectangle["right"])
            bottom = int(rectangle["bottom"])
        except (KeyError, TypeError, ValueError):
            return None
        if right <= left or bottom <= top:
            return []

        width = right - left
        height = bottom - top
        center_y = top + height // 2
        upper_y = top + max(6, min(height // 3, height - 4))
        content_x = left + min(max(width // 4, 12), max(width - 8, 1))
        points = [
            (content_x, center_y),
            (left + min(18, max(width - 4, 1)), center_y),
            (left + width // 2, center_y),
            (content_x, upper_y),
        ]
        return list(dict.fromkeys(points))

    def _clear_quote_mention_prefix(self) -> None:
        from pywinauto import keyboard

        keyboard.send_keys("{BACKSPACE}{BACKSPACE}")
        time.sleep(0.05)

    def _click_context_menu_item(self, labels: tuple[str, ...]) -> bool:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")
        deadline = time.perf_counter() + 1.5
        while time.perf_counter() < deadline:
            for window in desktop.windows(visible_only=True):
                control = self._find_named_descendant(window, labels, max_depth=4)
                if control is None:
                    continue
                try:
                    control.click_input()
                    time.sleep(0.1)
                    return True
                except Exception:
                    continue
            time.sleep(0.05)
        return False

    def _find_named_descendant(self, control: Any, labels: tuple[str, ...], *, max_depth: int) -> Any | None:
        normalized_labels = {self._normalize_text(label).casefold() for label in labels}
        stack: list[tuple[Any, int]] = [(control, 0)]
        while stack:
            current, depth = stack.pop()
            try:
                info = getattr(current, "element_info", None)
                name = self._normalize_text(str(getattr(info, "name", "") if info else current.window_text()))
            except Exception:
                name = ""
            if name.casefold() in normalized_labels:
                return current
            if depth >= max_depth:
                continue
            try:
                children = current.children()
            except Exception:
                continue
            for child in children:
                stack.append((child, depth + 1))
        return None

    def _find_window(self) -> Any:
        try:
            from pywinauto import Desktop
        except ImportError as error:
            raise RuntimeError("pywinauto is not installed") from error

        desktop = Desktop(backend="uia")
        windows = desktop.windows(visible_only=False)
        candidates = [window for window in windows if self._window_candidate_score(window) > 0]
        if not candidates:
            raise RuntimeError(
                "QQ conversation window not found. "
                f"Expected group title: {self.config.expected_group_name}; fallback regex: {self.config.window_title_regex}"
            )
        candidates.sort(key=self._window_candidate_score, reverse=True)
        return candidates[0]

    def _window_candidate_score(self, window: Any) -> int:
        try:
            title = self._normalize_text(str(window.window_text()))
        except Exception:
            return 0
        if not title:
            return 0

        score = 0
        expected = self._normalize_text(self.config.expected_group_name)
        if expected and title == expected:
            score += 1000
        elif expected and (expected in title or title in expected):
            score += 700
        elif re.search(self.config.window_title_regex, title):
            score += 100
        else:
            return 0

        try:
            if window.is_visible():
                score += 20
            if not window.is_minimized():
                score += 10
        except Exception:
            pass
        return score

    def _prepare_window_for_interaction(self, window: Any) -> bool:
        was_minimized = False
        try:
            was_minimized = bool(window.is_minimized())
        except Exception:
            return False
        if was_minimized:
            window.restore()
            time.sleep(0.2)
        try:
            window.set_focus()
        except Exception:
            pass
        return was_minimized

    def _restore_minimized(self, window: Any, was_minimized: bool) -> None:
        if not was_minimized:
            return
        try:
            window.minimize()
        except Exception:
            return

    def _scroll_to_latest(self, window: Any) -> None:
        try:
            window.set_focus()
            from pywinauto import keyboard

            keyboard.send_keys("{END}")
            time.sleep(0.1)
        except Exception:
            return

    def _scroll_page_up(self, window: Any) -> None:
        try:
            window.set_focus()
            from pywinauto import keyboard

            keyboard.send_keys("{PGUP}")
            time.sleep(0.15)
        except Exception:
            return

    def _read_context_snapshot(self, window: Any) -> QQReadResult:
        entries = self._control_entries(window)
        active_group_name = self._active_group_name_from_entries(window, entries)
        visible_items = self._visible_chat_items(window, entries)
        chat_messages = self._chat_messages(visible_items)
        return QQReadResult(
            active_group_name=active_group_name,
            expected_group_name=self.config.expected_group_name,
            target_sender_name=self.config.target_sender_name,
            bot_sender_name=self.config.bot_sender_name,
            group_matched=self._group_matches(active_group_name),
            visible_items=visible_items,
            chat_messages=chat_messages,
            target_messages=[
                message
                for message in chat_messages
                if self._same_sender(message.sender_name, self.config.target_sender_name)
            ][-10:],
        )

    def _merge_read_results(self, snapshots: list[QQReadResult]) -> QQReadResult:
        if not snapshots:
            return QQReadResult(
                active_group_name="",
                expected_group_name=self.config.expected_group_name,
                target_sender_name=self.config.target_sender_name,
                bot_sender_name=self.config.bot_sender_name,
                group_matched=False,
                visible_items=[],
                chat_messages=[],
                target_messages=[],
            )

        visible_items: list[dict[str, Any]] = []
        visible_seen: set[tuple[str, str, int, int, int, int]] = set()
        messages: list[QQChatMessage] = []
        message_seen: set[str] = set()

        for snapshot in snapshots:
            for item in snapshot.visible_items:
                rect = item.get("rectangle") or {}
                key = (
                    str(item.get("text", "")),
                    str(item.get("control_type", "")),
                    int(rect.get("left", 0)),
                    int(rect.get("top", 0)),
                    int(rect.get("right", 0)),
                    int(rect.get("bottom", 0)),
                )
                if key in visible_seen:
                    continue
                visible_seen.add(key)
                visible_items.append(item)

            for message in snapshot.chat_messages:
                if message.fingerprint in message_seen:
                    continue
                message_seen.add(message.fingerprint)
                messages.append(message)

        messages.sort(key=lambda item: (item.rectangle["top"], item.rectangle["left"], item.text))
        active_group_name = snapshots[0].active_group_name
        return QQReadResult(
            active_group_name=active_group_name,
            expected_group_name=self.config.expected_group_name,
            target_sender_name=self.config.target_sender_name,
            bot_sender_name=self.config.bot_sender_name,
            group_matched=self._group_matches(active_group_name),
            visible_items=visible_items,
            chat_messages=messages,
            target_messages=[
                message
                for message in messages
                if self._same_sender(message.sender_name, self.config.target_sender_name)
            ][-20:],
        )

    def _send_group_error(self, window: Any) -> dict[str, Any] | None:
        expected = self._normalize_text(self.config.expected_group_name)
        active = self._active_group_name(window)
        if not expected:
            return {
                "reason": "expected_group_missing",
                "active_group_name": active,
                "expected_group_name": "",
                "group_matched": False,
            }
        if not self._group_matches(active):
            return {
                "reason": "wrong_group",
                "active_group_name": active,
                "expected_group_name": expected,
                "group_matched": False,
            }
        return None

    def _active_group_name(self, window: Any) -> str:
        return self._active_group_name_from_entries(window, self._control_entries(window))

    def _active_group_name_from_entries(self, window: Any, entries: list[dict[str, Any]]) -> str:
        title = self._normalize_text(str(window.window_text()))
        if self._group_matches(title):
            return title

        window_rect = self._rectangle_value(window)
        if window_rect is None:
            return ""

        top_min = window_rect["top"] + 45
        top_max = window_rect["top"] + 100
        left_min = window_rect["left"] + 220

        for entry in entries:
            name = self._normalize_text(entry["name"])
            rect = entry["rectangle"]
            if not name or not rect:
                continue
            if entry["control_type"] not in {"Button", "Text", "Group"}:
                continue
            if rect["top"] < top_min or rect["top"] > top_max:
                continue
            if rect["left"] < left_min:
                continue
            if name in self._header_noise_names() or name.startswith("("):
                continue
            return name

        return ""

    def _group_matches(self, active_group_name: str) -> bool:
        expected = self._normalize_text(self.config.expected_group_name)
        active = self._normalize_text(active_group_name)
        return bool(expected and active == expected)

    def _control_entries(self, window: Any) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        self._collect_controls(window, depth=0, entries=entries)
        return entries

    def _visible_chat_items(self, window: Any, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        chat_rect = self._message_list_rect(window, entries)
        if chat_rect is None:
            return []

        left_min = chat_rect["left"]
        right_max = chat_rect["right"]
        top_min = chat_rect["top"]
        bottom_max = chat_rect["bottom"]
        seen: set[tuple[str, int, int]] = set()
        items: list[dict[str, Any]] = []

        for entry in entries:
            name = self._normalize_text(entry["name"])
            rect = entry["rectangle"]
            if not name or not rect:
                continue
            if entry["control_type"] not in {"Text", "Group", "Button"}:
                continue
            if rect["left"] < left_min or rect["right"] > right_max or rect["top"] < top_min or rect["bottom"] > bottom_max:
                continue
            if name in self._chat_noise_names() or name == self._normalize_text(self.config.expected_group_name):
                continue

            key = (name, int(rect["left"]), int(rect["top"]))
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "text": name,
                    "control_type": entry["control_type"],
                    "rectangle": rect,
                }
            )

        items.sort(key=lambda item: (item["rectangle"]["top"], item["rectangle"]["left"], item["text"]))
        return items[-60:]

    def _message_list_rect(self, window: Any, entries: list[dict[str, Any]]) -> dict[str, int] | None:
        for entry in entries:
            name = self._normalize_text(entry["name"])
            rect = entry["rectangle"]
            if name == "消息列表" and rect:
                return rect

        window_rect = self._rectangle_value(window)
        if window_rect is None:
            return None
        title = self._normalize_text(str(window.window_text()))
        if self._group_matches(title):
            return {
                "left": window_rect["left"] + 16,
                "top": window_rect["top"] + 82,
                "right": window_rect["right"] - 16,
                "bottom": window_rect["bottom"] - 150,
            }
        return {
            "left": window_rect["left"] + 220,
            "top": window_rect["top"] + 90,
            "right": window_rect["right"] - 180,
            "bottom": window_rect["bottom"] - 105,
        }

    def _target_chat_messages(self, visible_items: list[dict[str, Any]]) -> list[QQChatMessage]:
        target = self._normalize_text(self.config.target_sender_name)
        if not target:
            return []

        messages = [
            message
            for message in self._chat_messages(visible_items)
            if self._same_sender(message.sender_name, target)
        ]
        messages.sort(key=lambda item: (item.rectangle["top"], item.rectangle["left"], item.text))
        return messages[-10:]

    def _chat_messages(self, visible_items: list[dict[str, Any]]) -> list[QQChatMessage]:
        messages: list[QQChatMessage] = []
        seen: set[str] = set()
        sender_labels = self._sender_label_items(visible_items)
        sender_items = [item for item in sender_labels if not self._is_bot_sender(item["text"])]
        text_items = [item for item in visible_items if self._message_text_candidate(item, "")]

        for sender in sender_items:
            sender_name = self._normalize_text(sender["text"])
            sender_rect = sender["rectangle"]
            next_sender_top = self._next_sender_top(sender_labels, sender_rect["top"])
            nearby = [
                item
                for item in text_items
                if self._belongs_to_sender_block(item, sender_rect, next_sender_top)
            ]
            if not nearby:
                continue

            nearby.sort(key=lambda item: (item["rectangle"]["top"], item["rectangle"]["left"]))
            message_text = self._message_block_text(nearby)
            message_rect = self._merged_rectangle(nearby)
            fingerprint = self._message_fingerprint(sender_name, message_text, message_rect)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            messages.append(
                QQChatMessage(
                    sender_name=sender_name,
                    text=message_text,
                    fingerprint=fingerprint,
                    rectangle=message_rect,
                )
            )

        messages.sort(key=lambda item: (item.rectangle["top"], item.rectangle["left"], item.text))
        return messages[-10:]

    def _message_block_text(self, items: list[dict[str, Any]]) -> str:
        return "\n".join(self._normalize_text(item["text"]) for item in items if self._normalize_text(item["text"]))

    def _merged_rectangle(self, items: list[dict[str, Any]]) -> dict[str, int]:
        rectangles = [item["rectangle"] for item in items]
        return {
            "left": min(rect["left"] for rect in rectangles),
            "top": min(rect["top"] for rect in rectangles),
            "right": max(rect["right"] for rect in rectangles),
            "bottom": max(rect["bottom"] for rect in rectangles),
        }

    def _sender_label_items(self, visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            item
            for item in visible_items
            if self._looks_like_sender_label(item, visible_items)
        ]

    def _next_sender_top(self, sender_labels: list[dict[str, Any]], current_top: int) -> int | None:
        sender_tops = [
            item["rectangle"]["top"]
            for item in sender_labels
            if item["rectangle"]["top"] > current_top
        ]
        if not sender_tops:
            return None
        return min(sender_tops)

    def _looks_like_sender_label(self, item: dict[str, Any], visible_items: list[dict[str, Any]]) -> bool:
        text = self._normalize_text(item["text"])
        rect = item["rectangle"]
        if not text or not rect:
            return False
        if item["control_type"] != "Text":
            return False
        if text in self._chat_noise_names():
            return False
        return any(self._avatar_adjacent_to_label(rect, candidate) for candidate in visible_items)

    def _avatar_adjacent_to_label(self, label_rect: dict[str, int], item: dict[str, Any]) -> bool:
        if item["control_type"] != "Group":
            return False
        rect = item["rectangle"]
        if not rect:
            return False
        if abs(rect["top"] - label_rect["top"]) > 6:
            return False
        left_gap = abs(rect["right"] - label_rect["left"])
        right_gap = abs(label_rect["right"] - rect["left"])
        return left_gap <= 18 or right_gap <= 18

    def _belongs_to_sender_block(
        self,
        item: dict[str, Any],
        sender_rect: dict[str, int],
        next_sender_top: int | None,
    ) -> bool:
        rect = item["rectangle"]
        if rect["top"] < sender_rect["bottom"] - 2:
            return False
        if rect["top"] > sender_rect["bottom"] + 150:
            return False
        if next_sender_top is not None and rect["top"] >= next_sender_top - 2:
            return False
        if rect["left"] < sender_rect["left"] - 24:
            return False
        # QQNT outgoing bubbles can appear without a sender label.
        # Incoming text still starts near the sender label; right-side bubbles do not.
        if rect["left"] > sender_rect["left"] + 180:
            return False
        return True

    def _same_sender(self, value: str, target: str) -> bool:
        normalized = self._normalize_text(value)
        if not normalized or not target:
            return False
        return normalized == target or normalized in target or target in normalized

    def _is_bot_sender(self, value: str) -> bool:
        names = (self.config.bot_sender_name, *self.config.bot_sender_aliases)
        return any(self._same_sender(value, name) for name in names if name.strip())

    def _message_text_candidate(self, item: dict[str, Any], target: str) -> bool:
        text = self._normalize_text(item["text"])
        if not text:
            return False
        if item["control_type"] != "Text":
            return False
        if self._same_sender(text, target):
            return False
        if self._is_bot_sender(text):
            return False
        if text in self._chat_noise_names():
            return False
        if text.startswith("[") and text.endswith("]"):
            return False
        return True

    def _message_fingerprint(self, sender_name: str, text: str, rect: dict[str, int]) -> str:
        return "|".join(
            [
                self._normalize_text(sender_name),
                self._normalize_text(text),
                str(rect["left"]),
                str(rect["top"]),
                str(rect["right"]),
                str(rect["bottom"]),
            ]
        )

    def _collect_controls(self, control: Any, *, depth: int, entries: list[dict[str, Any]]) -> None:
        if depth > self.config.probe_max_depth:
            return
        if len(entries) >= self.config.probe_max_children:
            return

        entries.append(self._control_entry(control, depth))

        try:
            children = control.children()
        except Exception:
            return

        for child in children:
            if len(entries) >= self.config.probe_max_children:
                return
            self._collect_controls(child, depth=depth + 1, entries=entries)

    def _control_entry(self, control: Any, depth: int) -> dict[str, Any]:
        info = getattr(control, "element_info", None)
        return {
            "depth": depth,
            "name": str(getattr(info, "name", "") if info else ""),
            "class_name": str(getattr(info, "class_name", "") if info else ""),
            "control_type": str(getattr(info, "control_type", "") if info else ""),
            "rectangle": self._rectangle_value(control),
        }

    def _rectangle_value(self, control: Any) -> dict[str, int] | None:
        rectangle = getattr(control, "rectangle", lambda: None)()
        if rectangle is None:
            return None
        return {
            "left": rectangle.left,
            "top": rectangle.top,
            "right": rectangle.right,
            "bottom": rectangle.bottom,
        }

    def _normalize_text(self, value: str) -> str:
        decoded = html.unescape(value).replace("\xa0", " ")
        return re.sub(r"\s+", " ", decoded).strip()

    def _header_noise_names(self) -> set[str]:
        return {
            "语音通话",
            "视频通话",
            "屏幕共享",
            "群应用",
            "邀请加群",
            "更多",
        }

    def _chat_noise_names(self) -> set[str]:
        return {
            *self._header_noise_names(),
            "会话",
            "表情",
            "截图",
            "截图 弹出菜单",
            "文件",
            "文件弹出菜单",
            "图片",
            "红包",
            "语音消息",
            "聊天记录",
            "群主",
            "青铜",
        }
