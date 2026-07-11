from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
import inspect
import json
import time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from fastapi import WebSocket

from local_qq_agent.config import OneBotConfig


MessageListener = Callable[["OneBotMessage"], Awaitable[None] | None]


@dataclass(frozen=True)
class OneBotGroup:
    group_id: str
    group_name: str
    member_count: int = 0
    max_member_count: int = 0

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OneBotGroup":
        return cls(
            group_id=str(payload.get("group_id", "")),
            group_name=str(payload.get("group_name", "")),
            member_count=int(payload.get("member_count") or 0),
            max_member_count=int(payload.get("max_member_count") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "member_count": self.member_count,
            "max_member_count": self.max_member_count,
        }


@dataclass(frozen=True)
class OneBotMessage:
    message_id: str
    self_id: str
    group_id: str
    user_id: str
    sender_name: str
    text: str
    timestamp: int
    segments: tuple[dict[str, Any], ...] = ()
    reply_to_message_id: str = ""
    mentions_self: bool = False
    is_self: bool = False
    source: str = "event"
    raw_event: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def canonical_turn_id(self) -> str:
        return f"onebot:{self.self_id}:{self.message_id}"

    @property
    def fingerprint(self) -> str:
        return self.canonical_turn_id

    @property
    def rectangle(self) -> dict[str, int]:
        return {}

    @property
    def references_bot(self) -> bool:
        return bool(self.reply_to_message_id or self.mentions_self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_turn_id": self.canonical_turn_id,
            "message_id": self.message_id,
            "self_id": self.self_id,
            "group_id": self.group_id,
            "user_id": self.user_id,
            "sender_name": self.sender_name,
            "text": self.text,
            "timestamp": self.timestamp,
            "segments": list(self.segments),
            "reply_to_message_id": self.reply_to_message_id,
            "mentions_self": self.mentions_self,
            "references_bot": self.references_bot,
            "is_self": self.is_self,
            "source": self.source,
        }


@dataclass(frozen=True)
class OneBotSendResult:
    sent: bool
    reason: str
    text: str
    message_id: str = ""
    reply_to_message_id: str = ""
    retcode: int | None = None
    wording: str = ""
    duration_seconds: float = 0.0
    state: str = "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sent": self.sent,
            "reason": self.reason,
            "text": self.text,
            "message_id": self.message_id,
            "reply_to_message_id": self.reply_to_message_id,
            "retcode": self.retcode,
            "wording": self.wording,
            "duration_seconds": round(self.duration_seconds, 3),
            "state": self.state,
        }


@dataclass(frozen=True)
class OneBotStatus:
    connected: bool
    ready: bool
    self_id: str
    target_group_id: str
    target_group_name: str
    group_resolved: bool
    connected_at: float | None
    last_event_at: float | None
    last_message_id: str
    reconnect_count: int
    history_catchup_count: int
    detail: str
    auth_configured: bool
    auth_token_masked: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "ready": self.ready,
            "self_id": self.self_id,
            "target_group_id": self.target_group_id,
            "target_group_name": self.target_group_name,
            "group_resolved": self.group_resolved,
            "connected_at": self.connected_at,
            "last_event_at": self.last_event_at,
            "last_message_id": self.last_message_id,
            "reconnect_count": self.reconnect_count,
            "history_catchup_count": self.history_catchup_count,
            "detail": self.detail,
            "transport": "onebot11_reverse_websocket",
            "auth_configured": self.auth_configured,
            "auth_token_masked": self.auth_token_masked,
        }


class OneBotActionError(RuntimeError):
    def __init__(self, action: str, response: dict[str, Any]) -> None:
        self.action = action
        self.response = response
        super().__init__(
            f"OneBot action {action} failed: retcode={response.get('retcode')} "
            f"wording={response.get('wording') or response.get('message') or ''}"
        )


class OneBotGateway:
    def __init__(self, config: OneBotConfig) -> None:
        self.config = config
        self._socket: WebSocket | None = None
        self._socket_send_lock = asyncio.Lock()
        self._connection_lock = asyncio.Lock()
        self._pending_actions: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._listeners: list[MessageListener] = []
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=config.event_log_limit)
        self._self_id = ""
        self._target_group_id = config.target_group_id
        self._target_group_name = config.target_group_name
        self._group_resolved = bool(config.target_group_id)
        self._connected_at: float | None = None
        self._last_event_at: float | None = None
        self._last_message_id = ""
        self._reconnect_count = 0
        self._history_catchup_count = 0

    def add_message_listener(self, listener: MessageListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_message_listener(self, listener: MessageListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def status(self) -> OneBotStatus:
        connected = self._socket is not None
        ready = connected and bool(self._self_id) and self._group_resolved
        if ready:
            detail = "NapCat connected and target group resolved."
        elif not connected:
            detail = "Waiting for NapCat reverse WebSocket connection."
        elif not self._self_id:
            detail = "NapCat connected; waiting for bot identity."
        else:
            detail = "NapCat connected; select a target group."
        return OneBotStatus(
            connected=connected,
            ready=ready,
            self_id=self._self_id,
            target_group_id=self._target_group_id,
            target_group_name=self._target_group_name,
            group_resolved=self._group_resolved,
            connected_at=self._connected_at,
            last_event_at=self._last_event_at,
            last_message_id=self._last_message_id,
            reconnect_count=self._reconnect_count,
            history_catchup_count=self._history_catchup_count,
            detail=detail,
            auth_configured=bool(self.config.access_token),
            auth_token_masked=(f"...{self.config.access_token[-4:]}" if self.config.access_token else ""),
        )

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._recent_events)[-max(1, min(limit, self.config.event_log_limit)) :]

    async def serve(self, websocket: WebSocket) -> None:
        if not self._authorized(websocket):
            await websocket.close(code=1008, reason="invalid OneBot access token")
            return
        await websocket.accept()
        async with self._connection_lock:
            previous = self._socket
            if previous is not None and previous is not websocket:
                self._fail_pending_actions("OneBot WebSocket replaced by a newer NapCat connection")
                await previous.close(code=1012, reason="replaced by newer NapCat connection")
            self._socket = websocket
            self._connected_at = time.time()
            self._reconnect_count += 1
        bootstrap_task = asyncio.create_task(self._bootstrap_connection(), name="onebot-bootstrap")
        try:
            while True:
                payload = await websocket.receive_json()
                await self._handle_payload(payload)
        finally:
            if not bootstrap_task.done():
                bootstrap_task.cancel()
            was_current = self._socket is websocket
            if was_current:
                self._socket = None
                self._fail_pending_actions("OneBot WebSocket disconnected")

    async def call_action(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        socket = self._socket
        if socket is None:
            raise ConnectionError("NapCat is not connected")
        echo = f"agent-{uuid4().hex}"
        future = asyncio.get_running_loop().create_future()
        self._pending_actions[echo] = future
        payload = {"action": action, "params": params or {}, "echo": echo}
        try:
            async with self._socket_send_lock:
                await socket.send_json(payload)
            response = await asyncio.wait_for(
                future,
                timeout=timeout_seconds or self.config.action_timeout_seconds,
            )
        finally:
            self._pending_actions.pop(echo, None)
        if response.get("status") != "ok" or int(response.get("retcode") or 0) != 0:
            raise OneBotActionError(action, response)
        return response

    async def groups(self) -> list[OneBotGroup]:
        response = await self.call_action("get_group_list", {"no_cache": True})
        data = response.get("data") or []
        if not isinstance(data, list):
            return []
        return [OneBotGroup.from_payload(item) for item in data if isinstance(item, dict)]

    async def select_group(self, group_id: str, group_name: str = "") -> OneBotStatus:
        selected = str(group_id).strip()
        if not selected:
            raise ValueError("group_id must not be empty")
        groups = await self.groups()
        match = next((group for group in groups if group.group_id == selected), None)
        if match is None:
            raise ValueError(f"group_id is not visible to the bot: {selected}")
        self._target_group_id = match.group_id
        self._target_group_name = match.group_name or group_name.strip()
        self._group_resolved = True
        return self.status()

    async def resolve_configured_group(self) -> OneBotStatus:
        groups = await self.groups()
        match = None
        if self._target_group_id:
            match = next((group for group in groups if group.group_id == self._target_group_id), None)
        elif self._target_group_name:
            candidates = [group for group in groups if group.group_name == self._target_group_name]
            if len(candidates) == 1:
                match = candidates[0]
        if match is not None:
            self._target_group_id = match.group_id
            self._target_group_name = match.group_name
            self._group_resolved = True
        else:
            self._group_resolved = False
        return self.status()

    async def history(
        self,
        *,
        count: int = 30,
        timeout_seconds: float | None = None,
    ) -> list[OneBotMessage]:
        if not self._target_group_id:
            return []
        response = await self.call_action(
            "get_group_msg_history",
            {"group_id": self._target_group_id, "count": max(1, min(count, 100))},
            timeout_seconds=timeout_seconds,
        )
        data = response.get("data") or {}
        messages = data.get("messages", []) if isinstance(data, dict) else []
        parsed = [
            self._parse_group_message(item, source="history")
            for item in messages
            if isinstance(item, dict)
        ]
        return [message for message in parsed if message is not None]

    async def send_text(
        self,
        text: str,
        *,
        reply_to: OneBotMessage | None = None,
    ) -> OneBotSendResult:
        started_at = time.perf_counter()
        outgoing = text.strip()
        if not outgoing:
            return OneBotSendResult(False, "empty_text", text, duration_seconds=0.0)
        if not self.status().ready:
            return OneBotSendResult(False, "onebot_not_ready", outgoing, duration_seconds=0.0)
        segments: list[dict[str, Any]] = []
        reply_id = ""
        if reply_to is not None:
            reply_id = reply_to.message_id
            segments.append({"type": "reply", "data": {"id": reply_id}})
        segments.append({"type": "text", "data": {"text": outgoing}})
        try:
            response = await self.call_action(
                "send_group_msg",
                {"group_id": self._target_group_id, "message": segments},
                timeout_seconds=self.config.send_timeout_seconds,
            )
        except TimeoutError:
            reconciled = await self._reconcile_unknown_send(
                text=outgoing,
                reply_to_message_id=reply_id,
                started_at=time.time() - (time.perf_counter() - started_at),
            )
            if reconciled:
                return OneBotSendResult(
                    True,
                    "sent_reconciled",
                    outgoing,
                    message_id=reconciled,
                    reply_to_message_id=reply_id,
                    duration_seconds=time.perf_counter() - started_at,
                    state="sent",
                )
            return OneBotSendResult(
                False,
                "send_unknown",
                outgoing,
                reply_to_message_id=reply_id,
                duration_seconds=time.perf_counter() - started_at,
                state="unknown",
            )
        except Exception as error:
            response = getattr(error, "response", {})
            return OneBotSendResult(
                False,
                "send_failed",
                outgoing,
                reply_to_message_id=reply_id,
                retcode=response.get("retcode") if isinstance(response, dict) else None,
                wording=str(error),
                duration_seconds=time.perf_counter() - started_at,
            )
        data = response.get("data") or {}
        message_id = str(data.get("message_id", "")) if isinstance(data, dict) else ""
        return OneBotSendResult(
            True,
            "sent",
            outgoing,
            message_id=message_id,
            reply_to_message_id=reply_id,
            retcode=int(response.get("retcode") or 0),
            duration_seconds=time.perf_counter() - started_at,
            state="sent",
        )

    async def _reconcile_unknown_send(
        self,
        *,
        text: str,
        reply_to_message_id: str,
        started_at: float,
    ) -> str:
        try:
            messages = await self.history(count=20, timeout_seconds=1.0)
        except Exception:
            return ""
        for message in reversed(messages):
            if not message.is_self or message.text != text:
                continue
            if reply_to_message_id and message.reply_to_message_id != reply_to_message_id:
                continue
            if message.timestamp + 5 < int(started_at):
                continue
            return message.message_id
        return ""

    async def _bootstrap_connection(self) -> None:
        try:
            login = await self.call_action("get_login_info")
            data = login.get("data") or {}
            self._self_id = str(data.get("user_id", "")) if isinstance(data, dict) else ""
            await self.resolve_configured_group()
            if self._reconnect_count > 1 and self.status().ready:
                await self._catch_up_history()
        except Exception as error:
            self._recent_events.append(
                {"kind": "bootstrap_error", "created_at": time.time(), "error": str(error)}
            )

    async def _catch_up_history(self) -> None:
        messages = await self.history(count=self.config.startup_scrollback_readable_messages)
        self._history_catchup_count += len(messages)
        self._recent_events.append(
            {
                "kind": "history_catchup",
                "created_at": time.time(),
                "message_count": len(messages),
            }
        )
        for message in messages:
            catchup = OneBotMessage(**{**message.__dict__, "source": "history_catchup"})
            for listener in tuple(self._listeners):
                result = listener(catchup)
                if inspect.isawaitable(result):
                    await result

    async def _handle_payload(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        self._last_event_at = time.time()
        echo = str(payload.get("echo", ""))
        if echo:
            pending = self._pending_actions.get(echo)
            if pending is not None and not pending.done():
                pending.set_result(payload)
            return
        post_type = str(payload.get("post_type", ""))
        if post_type == "meta_event":
            self._recent_events.append(
                {
                    "kind": str(payload.get("meta_event_type", "meta_event")),
                    "created_at": self._last_event_at,
                }
            )
            return
        if post_type not in {"message", "message_sent"} or payload.get("message_type") != "group":
            return
        message = self._parse_group_message(payload, source="event")
        if message is None:
            return
        self._last_message_id = message.message_id
        self._recent_events.append({"kind": "group_message", **message.to_dict()})
        for listener in tuple(self._listeners):
            result = listener(message)
            if inspect.isawaitable(result):
                await result

    def _parse_group_message(self, payload: dict[str, Any], *, source: str) -> OneBotMessage | None:
        message_id = str(payload.get("message_id", "")).strip()
        group_id = str(payload.get("group_id", "")).strip()
        user_id = str(payload.get("user_id", "")).strip()
        if not message_id or not group_id or not user_id:
            return None
        sender = payload.get("sender") or {}
        sender_name = ""
        if isinstance(sender, dict):
            sender_name = str(sender.get("card") or sender.get("nickname") or "").strip()
        sender_name = sender_name or user_id
        raw_segments = payload.get("message")
        if isinstance(raw_segments, str):
            segments: tuple[dict[str, Any], ...] = ({"type": "text", "data": {"text": raw_segments}},)
        elif isinstance(raw_segments, list):
            segments = tuple(item for item in raw_segments if isinstance(item, dict))
        else:
            segments = ()
        text_parts: list[str] = []
        reply_id = ""
        mentions_self = False
        for segment in segments:
            kind = str(segment.get("type", ""))
            data = segment.get("data") or {}
            if not isinstance(data, dict):
                continue
            if kind == "text":
                text_parts.append(str(data.get("text", "")))
            elif kind == "reply":
                reply_id = str(data.get("id", ""))
            elif kind == "at" and str(data.get("qq", "")) == self._self_id:
                mentions_self = True
            elif kind in {"image", "face", "mface"}:
                text_parts.append(f"[{kind}]")
        text = "".join(text_parts).strip()
        self_id = str(payload.get("self_id") or self._self_id)
        return OneBotMessage(
            message_id=message_id,
            self_id=self_id,
            group_id=group_id,
            user_id=user_id,
            sender_name=sender_name,
            text=text,
            timestamp=int(payload.get("time") or time.time()),
            segments=segments,
            reply_to_message_id=reply_id,
            mentions_self=mentions_self,
            is_self=user_id == self_id or str(payload.get("post_type")) == "message_sent",
            source=source,
            raw_event=payload,
        )

    def _authorized(self, websocket: WebSocket) -> bool:
        expected = self.config.access_token
        if not expected:
            return websocket.client is not None and websocket.client.host in {"127.0.0.1", "::1"}
        authorization = websocket.headers.get("authorization", "")
        supplied = authorization.removeprefix("Bearer ").strip()
        supplied = supplied or websocket.query_params.get("access_token", "")
        return supplied == expected

    def _fail_pending_actions(self, detail: str) -> None:
        for future in self._pending_actions.values():
            if not future.done():
                future.set_exception(ConnectionError(detail))
        self._pending_actions.clear()
