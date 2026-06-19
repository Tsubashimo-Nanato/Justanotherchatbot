from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
import re
import time
from typing import Any, Callable
import unicodedata

from local_qq_agent.agent import LocalAgent
from local_qq_agent.agent.run_log import export_clean_run_log
from local_qq_agent.agent.turns import CleanTurn, clean_turn_text
from local_qq_agent.config import QQConfig
from local_qq_agent.memory import SQLiteMemoryStore
from local_qq_agent.paths import project_path
from local_qq_agent.qq import QQChatMessage, QQWindowAdapter
from local_qq_agent.server.turn_ledger import TurnLedger


@dataclass(frozen=True)
class LoopDecision:
    created_at: float
    message_text: str
    sender_name: str
    action: str
    reason: str
    sent: bool
    send_reason: str
    elapsed_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CleanedQQMessage:
    raw: QQChatMessage
    turn: CleanTurn
    identity: str

    @property
    def sender_name(self) -> str:
        return self.raw.sender_name

    @property
    def text(self) -> str:
        return self.turn.text

    @property
    def raw_text(self) -> str:
        return self.raw.text

    @property
    def fingerprint(self) -> str:
        return self.raw.fingerprint

    @property
    def references_bot(self) -> bool:
        return self.turn.references_bot

    @property
    def rectangle(self) -> dict[str, int]:
        return self.raw.rectangle

    def to_dict(self) -> dict[str, Any]:
        data = self.raw.to_dict()
        data["raw_text"] = self.raw.text
        data["clean_text"] = self.turn.text
        data["clean_identity"] = self.identity
        data["turn_cleaning"] = self.turn.to_metadata()
        return data


class AgentLoop:
    def __init__(
        self,
        *,
        agent: LocalAgent,
        qq: QQWindowAdapter,
        store: SQLiteMemoryStore,
        config: QQConfig,
        reboot_scheduler: Callable[[str], dict[str, Any]] | None = None,
        is_active_instance: Callable[[], bool] | None = None,
    ) -> None:
        self.agent = agent
        self.qq = qq
        self.store = store
        self.config = config
        self.reboot_scheduler = reboot_scheduler
        self.is_active_instance = is_active_instance
        self._task: asyncio.Task[None] | None = None
        self._processor_task: asyncio.Task[None] | None = None
        self._tick_lock = asyncio.Lock()
        self._qq_io_lock = asyncio.Lock()
        self._processor_wakeup = asyncio.Event()
        self._stop_requested = False
        self._processed_fingerprints: set[str] = set()
        self._context_fingerprints: set[str] = set()
        self._processed_text_times: dict[str, float] = {}
        self._processed_message_times: dict[str, float] = {}
        self._pending_messages: deque[CleanedQQMessage] = deque()
        self._queued_message_ids: set[str] = set()
        self._inflight_message_ids: set[str] = set()
        self._placeholder_message_times: dict[str, float] = {}
        self._turn_ledger = TurnLedger(ttl_seconds=config.duplicate_suppression_seconds)
        self._active_message: dict[str, Any] | None = None
        self._sent_texts: list[str] = []
        self._decisions: list[LoopDecision] = []
        self._next_read_allowed_at = 0.0
        self._idle_read_ticks = 0
        self._current_poll_interval_seconds = self._active_poll_interval()
        self._activity = self._activity_state(stage="idle", detail="Loop is not running.")
        self._session_start_event_id: int | None = None
        self._inactive_instance_recorded = False
        self._hydrate_processed_messages()

    def status(self) -> dict[str, Any]:
        task_done = self._task.done() if self._task else True
        processor_done = self._processor_task.done() if self._processor_task else True
        return {
            "running": self.running,
            "task_done": task_done,
            "processor_running": self._processor_task is not None and not processor_done,
            "processor_done": processor_done,
            "poll_interval_seconds": self.config.poll_interval_seconds,
            "idle_poll_interval_seconds": self.config.idle_poll_interval_seconds,
            "idle_poll_after_ticks": self.config.idle_poll_after_ticks,
            "current_poll_interval_seconds": self._current_poll_interval_seconds,
            "idle_read_ticks": self._idle_read_ticks,
            "read_timeout_seconds": self.config.read_timeout_seconds,
            "duplicate_suppression_seconds": self.config.duplicate_suppression_seconds,
            "max_messages_per_tick": self.config.max_messages_per_tick,
            "ignore_existing_on_start": self.config.ignore_existing_on_start,
            "target_sender_name": self.config.target_sender_name,
            "expected_group_name": self.config.expected_group_name,
            "processed_count": len(self._processed_fingerprints),
            "context_seen_count": len(self._context_fingerprints),
            "text_seen_count": len(self._processed_text_times),
            "message_seen_count": len(self._processed_message_times),
            "pending_message_count": len(self._pending_messages),
            "queued_message_count": len(self._queued_message_ids),
            "inflight_message_count": len(self._inflight_message_ids),
            "placeholder_seen_count": len(self._placeholder_message_times),
            "ledger": self._turn_ledger.summary(),
            "active_message": dict(self._active_message) if self._active_message else None,
            "pending_messages": [self._message_status(message) for message in list(self._pending_messages)[:20]],
            "inflight_message_ids": sorted(self._inflight_message_ids),
            "tick_busy": self._tick_lock.locked(),
            "stop_requested": self._stop_requested,
            "active_instance": self._is_active_instance(),
            "activity": dict(self._activity),
            "recent_decisions": [self._decision_status(decision) for decision in self._decisions[-12:]],
        }

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _is_active_instance(self) -> bool:
        if self.is_active_instance is None:
            return True
        try:
            return bool(self.is_active_instance())
        except Exception:
            return False

    def _stop_for_inactive_instance(self, stage: str) -> dict[str, Any]:
        self._stop_requested = True
        self._clear_pending_messages()
        self._set_activity(
            stage="inactive_instance",
            detail="Another FastAPI agent instance owns the runtime lease. This loop is stopped.",
            metadata={"source_stage": stage},
        )
        if not self._inactive_instance_recorded:
            self._inactive_instance_recorded = True
            if self.store is not None:
                self.store.append_event(
                    source="loop",
                    kind="loop_stopped_inactive_instance",
                    content="QQ loop stopped because another agent instance is active",
                    metadata={"source_stage": stage, "status": self.status()},
                )
        return {"ok": False, "reason": "inactive_agent_instance", "source_stage": stage}

    def _active_poll_interval(self) -> float:
        return max(self.config.poll_interval_seconds, 0.2)

    def _idle_poll_interval(self) -> float:
        return max(self.config.idle_poll_interval_seconds, self._active_poll_interval())

    def _next_poll_interval(self) -> float:
        return self._current_poll_interval_seconds

    def _record_read_activity(self, active: bool) -> None:
        if active:
            self._idle_read_ticks = 0
            self._current_poll_interval_seconds = self._active_poll_interval()
            return

        self._idle_read_ticks += 1
        if self._idle_read_ticks >= max(self.config.idle_poll_after_ticks, 1):
            self._current_poll_interval_seconds = self._idle_poll_interval()
            return

        self._current_poll_interval_seconds = self._active_poll_interval()

    async def start(self) -> dict[str, Any]:
        if self.running:
            return self.status()
        if not self._is_active_instance():
            self._stop_for_inactive_instance("start")
            return self.status()

        self._stop_requested = False
        self._clear_pending_messages()
        self._record_read_activity(True)
        baseline: dict[str, Any] | None = None
        if self.config.ignore_existing_on_start:
            self._set_activity(stage="baseline_reading", detail="Marking visible target messages as history.")
            baseline = await self._mark_visible_baseline()
            self._set_activity(
                stage="baseline_marked",
                detail="Startup baseline finished.",
                metadata={"baseline": baseline},
            )
            if not baseline.get("ok"):
                self._set_activity(
                    stage="baseline_failed",
                    detail="Loop did not start because startup baseline failed.",
                    metadata={"baseline": baseline},
                )
                self.store.append_event(
                    source="loop",
                    kind="loop_start_blocked",
                    content=f"QQ agent loop start blocked: {baseline.get('reason', 'baseline_failed')}",
                    metadata={"baseline": baseline, "status": self.status()},
                )
                return self.status()

        self._task = asyncio.create_task(self._run(), name="qq-agent-loop")
        self._processor_task = asyncio.create_task(self._process_pending_messages(), name="qq-agent-processor")
        self._set_activity(stage="running_idle", detail="Loop started. Waiting for new target messages.")
        start_event = self.store.append_event(
            source="loop",
            kind="loop_started",
            content="QQ agent loop started",
            metadata={**self.status(), "baseline": baseline},
        )
        self._session_start_event_id = start_event.id
        return self.status()

    async def stop(self) -> dict[str, Any]:
        if self._task is None:
            return self.status()
        if self._task.done():
            return self.status()

        self._stop_requested = True
        self._processor_wakeup.set()
        self._set_activity(stage="stopping", detail="Stop requested. Waiting for current tick to finish.")
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=max(self.config.poll_interval_seconds + 5, 5))
        except TimeoutError:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._processor_task is not None and not self._processor_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._processor_task), timeout=max(self.config.poll_interval_seconds + 5, 5))
            except TimeoutError:
                self._processor_task.cancel()
                try:
                    await self._processor_task
                except asyncio.CancelledError:
                    pass

        self.store.append_event(
            source="loop",
            kind="loop_stopped",
            content="QQ agent loop stopped",
            metadata=self.status(),
        )
        self._export_clean_run_log()
        self._set_activity(stage="stopped", detail="Loop stopped.")
        return self.status()

    def _export_clean_run_log(self) -> None:
        if self._session_start_event_id is None:
            return

        target_user = getattr(self.agent.persona_guard.config, "style_learning_target_user", "")
        output_dir = project_path("personality/nanato/memory/runtime/run_logs")
        try:
            result = export_clean_run_log(
                store=self.store,
                started_after_event_id=self._session_start_event_id,
                output_dir=output_dir,
                style_learning_target_user=target_user,
            )
        except Exception as error:
            self.store.append_event(
                source="loop",
                kind="run_log_export_failed",
                content="Clean run log export failed",
                metadata={"error": str(error), "session_start_event_id": self._session_start_event_id},
            )
            return

        self.store.append_event(
            source="loop",
            kind="run_log_exported",
            content=f"Clean run log exported: {result.get('path')}",
            metadata=result,
        )

    async def tick(self) -> dict[str, Any]:
        if not self._is_active_instance():
            return self._stop_for_inactive_instance("tick")

        if self._tick_lock.locked():
            self._set_activity(stage="tick_busy", detail="Tick skipped because another tick is still running.")
            return {"ok": False, "reason": "tick_already_running"}

        now = time.time()
        if now < self._next_read_allowed_at:
            self._set_activity(
                stage="read_backoff",
                detail="Waiting before the next QQ read after a timeout.",
                metadata={"retry_at": round(self._next_read_allowed_at, 3)},
            )
            return {"ok": False, "reason": "qq_read_backoff"}

        async with self._tick_lock:
            return await self._tick_unlocked()

    def record_visible_read(self, read_result) -> dict[str, Any]:
        if not read_result.group_matched:
            return {"contacts_seen": 0, "context_recorded": 0, "reason": "wrong_group"}

        before = len(self._context_fingerprints)
        self._initialize_visible_contacts(read_result.chat_messages)
        self._record_visible_context(read_result.chat_messages)
        return {
            "contacts_seen": len(read_result.chat_messages),
            "context_recorded": len(self._context_fingerprints) - before,
            "reason": "recorded",
        }

    async def collect_scrollback(self, *, pages: int = 3) -> dict[str, Any]:
        started_at = time.perf_counter()
        async with self._qq_io_lock:
            read_result = await asyncio.to_thread(self.qq.read_scrollback_context, pages=pages)

        if not read_result.group_matched:
            self._set_activity(
                stage="wrong_group",
                detail="Scrollback read found a different QQ group.",
                metadata={
                    "active_group_name": read_result.active_group_name,
                    "expected_group_name": read_result.expected_group_name,
                },
            )
            return {"ok": False, "reason": "wrong_group", "read": read_result.to_dict()}

        self._initialize_visible_contacts(read_result.chat_messages)
        enqueued = self._enqueue_visible_targets(read_result.chat_messages)
        context_result = self.record_visible_read(read_result)
        if enqueued:
            self._processor_wakeup.set()

        self._set_activity(
            stage="scrollback_collected",
            detail="Scrollback context was collected from QQ.",
            metadata={
                "pages": pages,
                "context": context_result,
                "enqueued_count": len(enqueued),
                "pending_message_count": len(self._pending_messages),
                "elapsed_seconds": round(time.perf_counter() - started_at, 3),
            },
        )
        return {
            "ok": True,
            "reason": "scrollback_collected",
            "elapsed_seconds": round(time.perf_counter() - started_at, 3),
            "context_recording": context_result,
            "enqueued": [message.to_dict() for message in enqueued],
            "pending_message_count": len(self._pending_messages),
            "read": read_result.to_dict(),
        }

    async def _tick_unlocked(self) -> dict[str, Any]:
        started_at = time.perf_counter()
        send_preflight = self._send_preflight()
        if not send_preflight["ok"]:
            self._set_activity(
                stage="send_blocked",
                detail=str(send_preflight["detail"]),
                metadata=send_preflight,
            )
            return send_preflight

        self._set_activity(stage="reading_window", detail="Reading visible QQ message list.")
        try:
            read_result = await self._read_visible_context("tick")
            self._next_read_allowed_at = 0.0
        except TimeoutError as error:
            self._next_read_allowed_at = time.time() + self.config.read_timeout_seconds
            self._set_activity(
                stage="read_timeout",
                detail="QQ visible context read timed out.",
                metadata={"error": str(error), "timeout_seconds": self.config.read_timeout_seconds},
            )
            self.store.append_event(
                source="loop",
                kind="loop_error",
                content="QQ visible context read timed out",
                metadata={"error": str(error), "timeout_seconds": self.config.read_timeout_seconds},
            )
            return {"ok": False, "reason": "qq_read_timeout", "error": str(error)}
        except Exception as error:
            self._set_activity(
                stage="read_error",
                detail="QQ visible context read failed.",
                metadata={"error": str(error)},
            )
            self.store.append_event(
                source="loop",
                kind="loop_error",
                content="QQ visible context read failed",
                metadata={"error": str(error)},
            )
            return {"ok": False, "reason": "qq_read_failed", "error": str(error)}

        if not read_result.group_matched:
            self._set_activity(
                stage="wrong_group",
                detail="Active QQ group does not match config.",
                metadata={
                    "active_group_name": read_result.active_group_name,
                    "expected_group_name": read_result.expected_group_name,
                },
            )
            self._record_skip(
                reason="wrong_group",
                message_text="",
                sender_name=self.config.target_sender_name,
                metadata=read_result.to_dict(),
                elapsed_seconds=time.perf_counter() - started_at,
            )
            return {"ok": False, "reason": "wrong_group", "read": read_result.to_dict()}

        self._initialize_visible_contacts(read_result.chat_messages)
        enqueued = self._enqueue_visible_targets(read_result.chat_messages)
        context_result = self.record_visible_read(read_result)
        self._record_read_activity(
            bool(enqueued) or bool(self._pending_messages) or int(context_result.get("context_recorded", 0)) > 0
        )
        if enqueued:
            self._processor_wakeup.set()

        handled: list[dict[str, Any]] = []
        if not handled:
            detail = "Queued messages are waiting." if self._pending_messages else "No new target messages."
            self._set_activity(
                stage="running_idle",
                detail=detail,
                metadata={
                    "visible_candidate_messages": len(read_result.chat_messages),
                    "enqueued_candidate_messages": len(enqueued),
                    "pending_message_count": len(self._pending_messages),
                    "idle_read_ticks": self._idle_read_ticks,
                    "next_poll_interval_seconds": self._next_poll_interval(),
                },
            )

        return {
            "ok": True,
            "reason": "tick_complete",
            "elapsed_seconds": round(time.perf_counter() - started_at, 3),
            "read": read_result.to_dict(),
            "enqueued": [message.to_dict() for message in enqueued],
            "handled": handled,
            "pending_message_count": len(self._pending_messages),
            "pending_unseen_count": len(self._pending_messages),
            "idle_read_ticks": self._idle_read_ticks,
            "next_poll_interval_seconds": self._next_poll_interval(),
        }

    async def _run(self) -> None:
        while not self._stop_requested:
            if not self._is_active_instance():
                self._stop_for_inactive_instance("run")
                break
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.store.append_event(
                    source="loop",
                    kind="loop_error",
                    content="QQ agent loop tick failed",
                    metadata={"error": str(error)},
                )
            if self._stop_requested:
                break
            await asyncio.sleep(self._next_poll_interval())

    async def _process_pending_messages(self) -> None:
        while not self._stop_requested:
            if not self._is_active_instance():
                self._stop_for_inactive_instance("processor")
                break
            if not self._pending_messages:
                self._processor_wakeup.clear()
                try:
                    await asyncio.wait_for(self._processor_wakeup.wait(), timeout=max(self.config.poll_interval_seconds, 0.2))
                except TimeoutError:
                    continue
                continue

            processed = await self._process_next_pending_message()
            if not processed:
                await asyncio.sleep(max(self.config.poll_interval_seconds, 0.2))

    async def _process_next_pending_message(self) -> LoopDecision | None:
        if not self._is_active_instance():
            self._stop_for_inactive_instance("process_next")
            return None

        send_preflight = self._send_preflight()
        if not send_preflight["ok"]:
            self._set_activity(
                stage="send_blocked",
                detail=str(send_preflight["detail"]),
                metadata={**send_preflight, "pending_message_count": len(self._pending_messages)},
            )
            return None

        while self._pending_messages:
            message = self._pending_messages.popleft()
            identity = message.identity
            self._queued_message_ids.discard(identity)
            if self._message_seen(message.sender_name, message.text, message.fingerprint):
                continue

            self._inflight_message_ids.add(identity)
            self._turn_ledger.mark_inflight(
                identity,
                metadata={"fingerprint": message.fingerprint, "raw_message_text": message.raw_text},
            )
            started_at = time.perf_counter()
            self._active_message = {
                "sender_name": message.sender_name,
                "message_text": message.text,
                "raw_message_text": message.raw_text,
                "fingerprint": message.fingerprint,
                "clean_identity": message.identity,
                "queued_remaining": len(self._pending_messages),
            }
            self._set_activity(
                stage="message_dequeued",
                detail="Queued target message selected for decision.",
                sender_name=message.sender_name,
                message_text=message.text,
                metadata={
                    "fingerprint": message.fingerprint,
                    "raw_message_text": message.raw_text,
                    "clean_identity": message.identity,
                    "turn_cleaning": message.turn.to_metadata(),
                    "queued_remaining": len(self._pending_messages),
                },
            )
            try:
                return await self._handle_message(message, started_at)
            except Exception:
                self._remember_seen_message(message.sender_name, message.text, message.fingerprint)
                raise
            finally:
                self._inflight_message_ids.discard(identity)
                self._active_message = None

        return None

    async def _handle_message(self, message: CleanedQQMessage | QQChatMessage, started_at: float) -> LoopDecision:
        if not isinstance(message, CleanedQQMessage):
            message = self._clean_visible_message(message)
        sender_name = message.sender_name
        text = message.text
        self._set_activity(
            stage="model_running",
            detail="Agent is deciding with the local model or command rules.",
            sender_name=sender_name,
            message_text=text,
        )
        result = await self.agent.respond_to_incoming(
            user_name=sender_name,
            message=text,
            placeholder_sender=lambda placeholder: self._send_placeholder(
                message=message,
                placeholder=placeholder,
            ),
            reply_to_bot=message.references_bot,
        )
        elapsed = time.perf_counter() - started_at
        self._set_activity(
            stage="model_done" if result.used_model else "agent_decided",
            detail=f"Agent decision: {result.action}.",
            sender_name=sender_name,
            message_text=text,
            metadata={
                "action": result.action,
                "reason": result.reason,
                "used_model": result.used_model,
                "latency_seconds": result.metadata.get("latency_seconds"),
                "prompt_tokens": result.metadata.get("prompt_tokens"),
                "completion_tokens": result.metadata.get("completion_tokens"),
                "tokens_per_second": result.metadata.get("tokens_per_second"),
                "thinking_level": result.metadata.get("thinking_level"),
                "max_thinking_level": result.metadata.get("max_thinking_level"),
                "requested_thinking_level": result.metadata.get("requested_thinking_level"),
                "thinking_complexity_level": result.metadata.get("thinking_complexity_level"),
                "thinking_directive": result.metadata.get("thinking_directive"),
                "web_used": result.metadata.get("web_used"),
                "web_query": result.metadata.get("web_query"),
                "gate_decision": result.metadata.get("gate_decision"),
                "placeholder_sent": result.metadata.get("placeholder_sent"),
                "placeholder_text": result.metadata.get("placeholder_text"),
            },
        )
        result.metadata.setdefault("message_identity", message.identity)
        result.metadata.setdefault("source_fingerprint", message.fingerprint)
        result.metadata.setdefault("raw_message_text", message.raw_text)
        result.metadata.setdefault("loop_turn_cleaning", message.turn.to_metadata())

        sent = False
        send_reason = "not_sent"
        send_result: dict[str, Any] | None = None
        if result.action == "reply" and result.reply:
            if not self._is_active_instance():
                self._stop_for_inactive_instance("before_send")
            if self._stop_requested:
                decision = LoopDecision(
                    created_at=time.time(),
                    message_text=text,
                    sender_name=sender_name,
                    action="skip",
                    reason="loop_stopped_before_send",
                    sent=False,
                    send_reason="not_sent",
                    elapsed_seconds=round(time.perf_counter() - started_at, 3),
                metadata={
                    **result.metadata,
                    "agent_action": result.action,
                    "agent_reason": result.reason,
                    "agent_reply": result.reply,
                    "message_identity": message.identity,
                    "source_fingerprint": message.fingerprint,
                    "raw_message_text": message.raw_text,
                    "loop_turn_cleaning": message.turn.to_metadata(),
                },
                )
                self._remember_decision(decision)
                self._remember_seen_message(sender_name, text, message.fingerprint)
                self._set_activity(
                    stage="skip",
                    detail="Loop stopped before send.",
                    sender_name=sender_name,
                    message_text=text,
                    metadata=asdict(decision),
                )
                return decision

            outgoing = self._outgoing_text(result, elapsed)
            self._set_activity(
                stage="sending",
                detail="Sending reply through QQ adapter.",
                sender_name=sender_name,
                message_text=text,
                metadata={"outgoing_preview": outgoing[:240]},
            )
            placeholder_sent = bool(result.metadata.get("placeholder_sent"))
            send_stage = "final_followup" if placeholder_sent else "final_reply"
            send_result = await self._send_quoted_text(
                message=message,
                text=outgoing,
                stage=send_stage,
                quote_reply=not placeholder_sent,
                allow_unquoted_fallback=True,
            )
            sent = bool(send_result.get("sent"))
            send_reason = str(send_result.get("reason", "unknown"))
            if sent:
                self._sent_texts.append(outgoing)
                self._sent_texts = self._sent_texts[-20:]
            if sent and result.metadata.get("reboot_requested"):
                result.metadata["reboot_schedule"] = self._schedule_reboot("qq_command")

        decision = LoopDecision(
            created_at=time.time(),
            message_text=text,
            sender_name=sender_name,
            action=result.action,
            reason=result.reason,
            sent=sent,
            send_reason=send_reason,
            elapsed_seconds=round(time.perf_counter() - started_at, 3),
            metadata={**result.metadata, "send_result": send_result},
        )
        decision.metadata["message_identity"] = message.identity
        decision.metadata["source_fingerprint"] = message.fingerprint
        decision.metadata["raw_message_text"] = message.raw_text
        decision.metadata["loop_turn_cleaning"] = message.turn.to_metadata()
        self._remember_decision(decision)
        self._remember_seen_message(sender_name, text, message.fingerprint)
        if decision.action == "no_reply":
            stage = "no_reply"
            detail = "Agent decided not to reply."
        elif decision.sent:
            stage = "sent"
            detail = "Reply sent through QQ adapter."
        elif decision.send_reason != "not_sent":
            stage = "send_blocked"
            detail = f"QQ send did not execute: {decision.send_reason}."
        else:
            stage = "decision_recorded"
            detail = f"Agent decision recorded: {decision.action}."
        self._set_activity(
            stage=stage,
            detail=detail,
            sender_name=sender_name,
            message_text=text,
            metadata=asdict(decision),
        )
        return decision

    async def _send_placeholder(self, *, message: CleanedQQMessage | QQChatMessage, placeholder: str) -> dict[str, Any]:
        if not self._is_active_instance():
            self._stop_for_inactive_instance("placeholder")
            return {"sent": False, "reason": "inactive_agent_instance"}
        if self._stop_requested:
            return {"sent": False, "reason": "loop_stopped_before_placeholder"}

        cleaned = message if isinstance(message, CleanedQQMessage) else self._clean_visible_message(message)
        if self._placeholder_already_sent(cleaned.identity):
            return {
                "sent": False,
                "reason": "placeholder_already_sent_for_message",
                "message_identity": cleaned.identity,
            }
        self._remember_placeholder(cleaned.identity)

        self._set_activity(
            stage="sending_placeholder",
            detail="Sending a short wait message before slower processing.",
            sender_name=cleaned.sender_name,
            message_text=cleaned.text,
            metadata={"placeholder_preview": placeholder[:120]},
        )
        result = await self._send_quoted_text(
            message=cleaned,
            text=placeholder,
            stage="placeholder",
        )
        if result.get("sent"):
            self._sent_texts.append(placeholder)
            self._sent_texts = self._sent_texts[-20:]
        return result

    async def _send_quoted_text(
        self,
        *,
        message: CleanedQQMessage | QQChatMessage,
        text: str,
        stage: str,
        quote_reply: bool = True,
        allow_unquoted_fallback: bool = False,
    ) -> dict[str, Any]:
        async with self._qq_io_lock:
            if not quote_reply:
                return await self._send_unquoted_text_unlocked(text=text, stage=stage, mode="followup_unquoted")

            target, quote_refresh = await self._fresh_quote_target_unlocked(message)
            if target is None:
                if allow_unquoted_fallback:
                    result = await self._send_unquoted_text_unlocked(
                        text=text,
                        stage=stage,
                        mode="quote_fallback_unquoted",
                    )
                    verification = result.setdefault("verification", {})
                    if isinstance(verification, dict):
                        verification["quote_refresh"] = quote_refresh
                        verification["quote_fallback"] = "unquoted_after_missing_quote_target"
                    return result
                return {
                    "sent": False,
                    "dry_run": self.config.dry_run,
                    "reason": "quote_target_not_visible",
                    "text": text,
                    "verification": {"quote_refresh": quote_refresh, "stage": stage},
                    "duration_seconds": 0.0,
                }

            send_result = await asyncio.to_thread(self.qq.send_text, text, reply_to=target)
            result = send_result.to_dict()
            verification = result.setdefault("verification", {})
            if isinstance(verification, dict):
                verification["quote_refresh"] = quote_refresh
                verification["stage"] = stage
            return result

    async def _send_unquoted_text_unlocked(self, *, text: str, stage: str, mode: str) -> dict[str, Any]:
        send_result = await asyncio.to_thread(self.qq.send_text, text, reply_to=None)
        result = send_result.to_dict()
        verification = result.setdefault("verification", {})
        if isinstance(verification, dict):
            verification["stage"] = stage
            verification["mode"] = mode
        return result

    async def _fresh_quote_target(self, message: CleanedQQMessage | QQChatMessage) -> tuple[QQChatMessage | None, dict[str, Any]]:
        async with self._qq_io_lock:
            return await self._fresh_quote_target_unlocked(message)

    async def _fresh_quote_target_unlocked(self, message: CleanedQQMessage | QQChatMessage) -> tuple[QQChatMessage | None, dict[str, Any]]:
        original = message if isinstance(message, CleanedQQMessage) else self._clean_visible_message(message)
        try:
            read_result = await self._read_visible_context_unlocked("quote_target")
        except Exception as error:
            return None, {
                "ok": False,
                "reason": "quote_target_read_failed",
                "error": str(error),
                "original": original.to_dict(),
            }

        for candidate in read_result.chat_messages:
            if candidate.fingerprint == original.fingerprint:
                return candidate, {
                    "ok": True,
                    "reason": "fingerprint_match",
                    "original": original.to_dict(),
                    "target": candidate.to_dict(),
                }

        matching_text: list[CleanedQQMessage] = []
        for candidate in read_result.chat_messages:
            cleaned = self._clean_visible_message(candidate)
            if cleaned.identity == original.identity:
                matching_text.append(cleaned)
        if matching_text:
            target = matching_text[-1]
            return target.raw, {
                "ok": True,
                "reason": "clean_identity_match",
                "original": original.to_dict(),
                "target": target.to_dict(),
            }

        return None, {
            "ok": False,
            "reason": "quote_target_not_visible",
            "visible_count": len(read_result.chat_messages),
            "original": original.to_dict(),
        }

    def _schedule_reboot(self, reason: str) -> dict[str, Any]:
        if self.reboot_scheduler is None:
            return {"scheduled": False, "reason": "reboot_scheduler_not_configured"}

        try:
            schedule = self.reboot_scheduler(reason)
        except Exception as error:
            self.store.append_event(
                source="loop",
                kind="reboot_schedule_failed",
                content="Agent reboot schedule failed",
                metadata={"error": str(error), "reason": reason},
            )
            return {"scheduled": False, "reason": "schedule_failed", "error": str(error)}

        self.store.append_event(
            source="loop",
            kind="reboot_scheduled",
            content="Agent service reboot scheduled",
            metadata=schedule,
        )
        return schedule

    async def _mark_visible_baseline(self) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            read_result = await self._read_visible_context("baseline")
        except TimeoutError as error:
            self.store.append_event(
                source="loop",
                kind="loop_error",
                content="QQ baseline read timed out",
                metadata={"error": str(error), "timeout_seconds": self.config.read_timeout_seconds},
            )
            return {"ok": False, "reason": "qq_read_timeout", "error": str(error)}
        except Exception as error:
            self.store.append_event(
                source="loop",
                kind="loop_error",
                content="QQ baseline read failed",
                metadata={"error": str(error)},
            )
            return {"ok": False, "reason": "qq_read_failed", "error": str(error)}

        if not read_result.group_matched:
            return {
                "ok": False,
                "reason": "wrong_group",
                "active_group_name": read_result.active_group_name,
                "expected_group_name": read_result.expected_group_name,
            }

        marked = 0
        for message in read_result.chat_messages:
            cleaned = self._clean_visible_message(message)
            if not cleaned.text:
                self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
                continue
            if self._is_bot_sender(cleaned.sender_name):
                self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
                continue
            if self._message_seen(cleaned.sender_name, cleaned.text, cleaned.fingerprint):
                continue
            if self._looks_like_own_visible_message(cleaned):
                continue
            self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
            marked += 1

        self.record_visible_read(read_result)

        return {
            "ok": True,
            "reason": "baseline_marked",
            "marked_count": marked,
            "elapsed_seconds": round(time.perf_counter() - started_at, 3),
            "active_group_name": read_result.active_group_name,
        }

    async def _read_visible_context(self, operation: str):
        async with self._qq_io_lock:
            return await self._read_visible_context_unlocked(operation)

    async def _read_visible_context_unlocked(self, operation: str):
        timeout = self.config.read_timeout_seconds
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.qq.read_visible_context, passive=True),
                timeout=timeout,
            )
        except TimeoutError as error:
            raise TimeoutError(f"QQ read timed out during {operation} after {timeout:.1f}s") from error

    def _next_unseen_messages(
        self,
        messages: list[QQChatMessage],
    ) -> list[QQChatMessage]:
        return self._unseen_target_messages(messages)[: max(self.config.max_messages_per_tick, 1)]

    def _unseen_target_messages(self, messages: list[QQChatMessage]) -> list[QQChatMessage]:
        candidates: list[QQChatMessage] = []
        for message in messages:
            cleaned = self._clean_visible_message(message)
            if not cleaned.text:
                self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
                continue
            if self._is_bot_sender(cleaned.sender_name):
                self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
                continue
            if self._message_seen(cleaned.sender_name, cleaned.text, cleaned.fingerprint):
                continue
            if self._message_queued(cleaned):
                continue
            if self._looks_like_own_visible_message(cleaned):
                self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
                continue
            candidates.append(message)
        return candidates

    def _enqueue_visible_targets(self, messages: list[QQChatMessage]) -> list[CleanedQQMessage]:
        enqueued: list[CleanedQQMessage] = []
        for message in messages:
            cleaned = self._clean_visible_message(message)
            if not cleaned.text:
                self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
                continue
            if self._is_bot_sender(cleaned.sender_name):
                self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
                continue
            if self._message_seen(cleaned.sender_name, cleaned.text, cleaned.fingerprint):
                continue
            if self._message_queued(cleaned):
                continue
            if self._looks_like_own_visible_message(cleaned):
                self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
                continue

            self._pending_messages.append(cleaned)
            self._queued_message_ids.add(cleaned.identity)
            self._turn_ledger.mark_queued(
                cleaned.identity,
                metadata={"fingerprint": cleaned.fingerprint, "raw_message_text": cleaned.raw_text},
            )
            self._record_context_message(cleaned, agent_reason="queued_for_decision", agent_action="queued")
            enqueued.append(cleaned)

        if enqueued:
            self._set_activity(
                stage="messages_queued",
                detail="Visible target messages were queued for ordered processing.",
                metadata={
                    "enqueued_count": len(enqueued),
                    "pending_message_count": len(self._pending_messages),
                    "messages": [self._message_status(message) for message in enqueued],
                },
            )
        return enqueued

    def _clean_visible_message(self, message: QQChatMessage) -> CleanedQQMessage:
        turn = clean_turn_text(
            message.text,
            recent_bot_texts=tuple(self._sent_texts),
            quote_sender_names=self._quote_sender_names(),
        )
        identity = self._message_identity(message.sender_name, turn.text)
        self._turn_ledger.observe(
            turn_id=identity,
            sender=message.sender_name,
            clean_text=turn.text,
            raw_text=message.text,
            fingerprint=message.fingerprint,
            references_bot=turn.references_bot,
            metadata={"rectangle": message.rectangle, "turn_cleaning": turn.to_metadata()},
        )
        return CleanedQQMessage(raw=message, turn=turn, identity=identity)

    def _quote_sender_names(self) -> tuple[str, ...]:
        names: list[str] = []
        if self.config.bot_sender_name:
            names.append(self.config.bot_sender_name)
        names.extend(self.config.bot_sender_aliases)

        guard = getattr(self.agent, "persona_guard", None)
        aliases = getattr(guard, "reply_aliases", ()) if guard is not None else ()
        names.extend(str(alias) for alias in aliases if str(alias).strip())

        seen: set[str] = set()
        unique: list[str] = []
        for name in names:
            key = self._stable_text(name)
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(name)
        return tuple(unique)

    def _send_preflight(self) -> dict[str, Any]:
        model_preflight = getattr(getattr(self.agent, "model_client", None), "cloud_loop_preflight", None)
        if callable(model_preflight):
            result = model_preflight()
            if not result.get("ok", False):
                return {
                    "ok": False,
                    "reason": result.get("reason", "provider_blocked"),
                    "detail": result.get("detail", "Provider is not ready for QQ loop."),
                    "provider": result,
                }

        if self.config.dry_run or not self.config.send_requires_armed:
            return {"ok": True, "reason": "send_allowed"}

        status = self.qq.status()
        status_dict = status.to_dict()
        if status.armed:
            return {"ok": True, "reason": "send_allowed", "qq": status_dict}

        return {
            "ok": False,
            "reason": "qq_not_armed",
            "detail": "QQ adapter is not armed. No messages were read or consumed.",
            "qq": status_dict,
        }

    def _initialize_visible_contacts(self, messages: list[QQChatMessage]) -> None:
        for message in messages:
            if self._is_bot_sender(message.sender_name):
                continue
            affinity = 1.0 if self._same_sender(message.sender_name, self.config.target_sender_name) else 0.5
            source = "target_contact_seed" if affinity >= 1.0 else "visible_contact_seed"
            self.agent.social_state.ensure_contact(
                user_name=message.sender_name,
                initial_affinity=affinity,
                source=source,
            )

    def _record_visible_context(self, messages: list[QQChatMessage]) -> None:
        for message in messages:
            if self._is_bot_sender(message.sender_name):
                continue
            cleaned = self._clean_visible_message(message)
            if self._message_queued(cleaned) or self._message_seen(cleaned.sender_name, cleaned.text, cleaned.fingerprint):
                continue
            if self._looks_like_own_visible_message(cleaned):
                self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
                continue
            if self._same_sender(cleaned.sender_name, self.config.target_sender_name):
                continue
            self._record_context_message(cleaned, agent_reason="visible_context")

    def _record_context_message(
        self,
        message: QQChatMessage | CleanedQQMessage,
        *,
        agent_reason: str,
        agent_action: str = "context_only",
    ) -> None:
        cleaned = message if isinstance(message, CleanedQQMessage) else self._clean_visible_message(message)
        if not cleaned.text:
            return
        if self.store is None:
            return
        if cleaned.fingerprint in self._context_fingerprints:
            return
        self._context_fingerprints.add(cleaned.fingerprint)
        self.store.append_event(
            source=cleaned.sender_name,
            kind="group_message",
            content=cleaned.text,
            metadata={
                "origin": "qq_loop",
                "sender_name": cleaned.sender_name,
                "clean_text": cleaned.text,
                "agent_action": agent_action,
                "agent_reason": agent_reason,
                "fingerprint": cleaned.fingerprint,
                "rectangle": cleaned.rectangle,
                "raw_message_text": cleaned.raw_text,
                "clean_identity": cleaned.identity,
                "turn_cleaning": cleaned.turn.to_metadata(),
            },
        )

    def _set_activity(
        self,
        *,
        stage: str,
        detail: str,
        sender_name: str = "",
        message_text: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._activity = self._activity_state(
            stage=stage,
            detail=detail,
            sender_name=sender_name,
            message_text=message_text,
            metadata=metadata,
        )

    def _activity_state(
        self,
        *,
        stage: str,
        detail: str,
        sender_name: str = "",
        message_text: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "stage": stage,
            "detail": detail,
            "sender_name": sender_name,
            "message_text": message_text,
            "updated_at": round(time.time(), 3),
            "metadata": metadata or {},
        }

    def _outgoing_text(self, result, elapsed_seconds: float) -> str:
        reply = result.reply.strip()
        additions: list[str] = []
        if result.metadata.get("debug_requested"):
            metrics = self._format_debug_metrics(result.metadata, elapsed_seconds)
            if metrics:
                additions.append(metrics)
        if result.metadata.get("diagnostic_requested"):
            diagnostics = self._format_diagnostic_metrics(result.metadata)
            if diagnostics:
                additions.append(diagnostics)
        if not additions:
            return reply
        return "\n".join([reply, *additions])

    def _format_debug_metrics(self, metadata: dict[str, Any], elapsed_seconds: float) -> str:
        tps = metadata.get("tokens_per_second") or {}
        usage = metadata.get("usage") or {}
        return (
            "[debug "
            f"elapsed={elapsed_seconds:.3f}s, "
            f"model_latency={metadata.get('latency_seconds', '?')}s, "
            f"completion_tok_s={tps.get('completion_tokens', '?')}, "
            f"prompt_tokens={metadata.get('prompt_tokens') or usage.get('prompt_tokens', '?')}, "
            f"completion_tokens={metadata.get('completion_tokens') or usage.get('completion_tokens', '?')}, "
            f"total_tokens={metadata.get('total_tokens') or usage.get('total_tokens', '?')}, "
            f"requested_thinking={metadata.get('requested_thinking_level', '?')}, "
            f"thinking_level={metadata.get('thinking_level', '?')}, "
            f"web_used={metadata.get('web_used', False)}, "
            f"search_used={metadata.get('search_used', False)}, "
            f"local_time_used={metadata.get('local_time_used', False)}]"
        )

    def _format_diagnostic_metrics(self, metadata: dict[str, Any]) -> str:
        turn = metadata.get("loop_turn_cleaning") or metadata.get("turn_cleaning") or {}
        removed_lines = turn.get("removed_lines") if isinstance(turn, dict) else []
        web_sources = metadata.get("web_sources") or []
        return (
            "[diagnostic "
            f"event_id={metadata.get('assistant_event_id', 'pending')}, "
            f"clean_reason={turn.get('reason', '?') if isinstance(turn, dict) else '?'}, "
            f"removed_lines={len(removed_lines) if isinstance(removed_lines, (list, tuple)) else 0}, "
            f"requested_thinking={metadata.get('requested_thinking_level')}, "
            f"effective_thinking={metadata.get('thinking_level')}, "
            f"web_query={metadata.get('web_query') or 'none'}, "
            f"sources={len(web_sources)}, "
            f"message_identity={metadata.get('message_identity', 'pending')}]"
        )

    def _record_skip(
        self,
        *,
        reason: str,
        message_text: str,
        sender_name: str,
        metadata: dict[str, Any],
        elapsed_seconds: float,
    ) -> None:
        decision = LoopDecision(
            created_at=time.time(),
            message_text=message_text,
            sender_name=sender_name,
            action="skip",
            reason=reason,
            sent=False,
            send_reason="not_sent",
            elapsed_seconds=round(elapsed_seconds, 3),
            metadata=metadata,
        )
        self._remember_decision(decision)

    def _remember_decision(self, decision: LoopDecision) -> None:
        self._decisions.append(decision)
        self._decisions = self._decisions[-50:]
        self.store.append_event(
            source="loop",
            kind="loop_decision",
            content=f"{decision.action}: {decision.reason}",
            metadata=asdict(decision),
        )

    def _looks_like_own_reply(self, text: str) -> bool:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return True
        for line in lines:
            if any(line == sent or line in sent or sent in line for sent in self._sent_texts):
                return True
        return False

    def _looks_like_own_visible_message(self, message: CleanedQQMessage) -> bool:
        if self._looks_like_own_reply(message.text):
            return True
        if message.references_bot:
            return False
        if self._looks_like_own_reply(message.raw_text):
            return True
        return any(self._looks_like_own_reply(line) for line in message.turn.removed_lines)

    def _message_status(self, message: CleanedQQMessage) -> dict[str, Any]:
        return {
            "sender_name": message.sender_name,
            "message_text": message.text,
            "raw_message_text": message.raw_text,
            "fingerprint": message.fingerprint,
            "clean_identity": message.identity,
            "references_bot": message.references_bot,
            "turn_cleaning": message.turn.to_metadata(),
        }

    def _decision_status(self, decision: LoopDecision) -> dict[str, Any]:
        return {
            "created_at": decision.created_at,
            "message_text": decision.message_text,
            "sender_name": decision.sender_name,
            "action": decision.action,
            "reason": decision.reason,
            "sent": decision.sent,
            "send_reason": decision.send_reason,
            "elapsed_seconds": decision.elapsed_seconds,
            "metadata": self._status_metadata(decision.metadata),
        }

    def _status_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        allowed = (
            "raw_model_content",
            "cleaned_reply",
            "agent_reply",
            "latency_seconds",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "usage",
            "tokens_per_second",
            "thinking_level",
            "max_thinking_level",
            "requested_thinking_level",
            "thinking_complexity_level",
            "gate_decision",
            "placeholder_sent",
            "placeholder_text",
            "web_used",
            "local_time_used",
            "search_used",
            "browser_used",
            "web_query",
            "web_sources",
            "web_error",
            "math_used",
            "math_query",
            "math_result",
            "message_identity",
            "source_fingerprint",
            "raw_message_text",
            "loop_turn_cleaning",
            "send_result",
            "stage_timings",
            "provider_decision",
            "provider_trace_id",
            "provider_parse_status",
            "provider_decision_json",
        )
        result: dict[str, Any] = {}
        for key in allowed:
            if key not in metadata:
                continue
            result[key] = self._status_value(metadata[key])
        return result

    def _status_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return value if len(value) <= 2000 else f"{value[:2000]}... [truncated {len(value) - 2000} chars]"
        if isinstance(value, list):
            return [self._status_value(item) for item in value[:20]]
        if isinstance(value, dict):
            compact: dict[str, Any] = {}
            for key, item in value.items():
                if key in {"memory_context", "memory_lines", "memory_operation"}:
                    continue
                compact[str(key)] = self._status_value(item)
            return compact
        return value

    def _message_seen(self, sender_name: str, text: str, fingerprint: str) -> bool:
        self._prune_seen_messages()
        identity = self._message_identity(sender_name, text)
        if self._turn_ledger.is_closed(identity, fingerprint):
            return True
        if fingerprint in self._processed_fingerprints:
            return True
        if identity in self._processed_message_times:
            return True
        return self._text_key(sender_name, text) in self._processed_text_times

    def _placeholder_already_sent(self, identity: str) -> bool:
        self._prune_placeholder_messages()
        return identity in self._placeholder_message_times

    def _remember_placeholder(self, identity: str) -> None:
        self._prune_placeholder_messages()
        self._placeholder_message_times[identity] = time.time()

    def _message_queued(self, message: QQChatMessage | CleanedQQMessage) -> bool:
        cleaned = message if isinstance(message, CleanedQQMessage) else self._clean_visible_message(message)
        return (
            cleaned.identity in self._queued_message_ids
            or cleaned.identity in self._inflight_message_ids
            or not self._turn_ledger.can_enqueue(cleaned.identity, cleaned.fingerprint)
        )

    def _same_sender(self, value: str, target: str) -> bool:
        normalized = value.strip()
        expected = target.strip()
        if not normalized or not expected:
            return False
        return normalized == expected or normalized in expected or expected in normalized

    def _is_bot_sender(self, sender_name: str) -> bool:
        names = (self.config.bot_sender_name, *self.config.bot_sender_aliases)
        return any(self._same_sender(sender_name, name) for name in names if name.strip())

    def _remember_seen_message(self, sender_name: str, text: str, fingerprint: str) -> None:
        seen_at = time.time()
        identity = self._message_identity(sender_name, text)
        self._processed_fingerprints.add(fingerprint)
        self._processed_text_times[self._text_key(sender_name, text)] = seen_at
        self._processed_message_times[identity] = seen_at
        self._turn_ledger.mark_completed(identity, metadata={"fingerprint": fingerprint})

    def _clear_pending_messages(self) -> None:
        self._pending_messages.clear()
        self._queued_message_ids.clear()
        self._inflight_message_ids.clear()
        self._turn_ledger.clear_active()
        self._active_message = None

    def _prune_seen_messages(self) -> None:
        cutoff = time.time() - max(self.config.duplicate_suppression_seconds, 120.0)
        self._processed_text_times = {
            key: seen_at for key, seen_at in self._processed_text_times.items() if seen_at >= cutoff
        }
        self._processed_message_times = {
            key: seen_at for key, seen_at in self._processed_message_times.items() if seen_at >= cutoff
        }

    def _prune_placeholder_messages(self) -> None:
        cutoff = time.time() - max(self.config.duplicate_suppression_seconds, 120.0)
        self._placeholder_message_times = {
            key: sent_at for key, sent_at in self._placeholder_message_times.items() if sent_at >= cutoff
        }

    def _text_key(self, sender_name: str, text: str) -> str:
        return self._message_identity(sender_name, text)

    def _message_identity(self, sender_name: str, text: str) -> str:
        return f"{self._stable_text(sender_name)}|{self._stable_text(text)}"

    def _stable_text(self, value: str) -> str:
        text = unicodedata.normalize("NFKC", value or "")
        text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
        text = re.sub(r"\s+", " ", text).strip()
        return text.casefold()

    def _hydrate_processed_messages(self) -> None:
        if self.store is None:
            return

        cutoff = time.time() - max(self.config.duplicate_suppression_seconds, 120.0)
        try:
            events = self.store.recent_events(limit=500, newest_first=True)
        except Exception:
            return

        for event in events:
            if event.kind != "loop_decision":
                continue
            seen_at = self._event_timestamp(event.created_at)
            if seen_at < cutoff:
                continue

            metadata = event.metadata or {}
            decision_metadata = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
            sender_name = str(metadata.get("sender_name", ""))
            message_text = str(metadata.get("message_text", ""))
            if not sender_name or not message_text:
                continue

            identity = (
                str(metadata.get("message_identity", ""))
                or str(decision_metadata.get("message_identity", ""))
                or self._message_identity(sender_name, message_text)
            )
            self._processed_message_times[identity] = seen_at
            self._turn_ledger.observe(
                turn_id=identity,
                sender=sender_name,
                clean_text=message_text,
                raw_text=str(decision_metadata.get("raw_message_text", message_text)),
                fingerprint=str(decision_metadata.get("source_fingerprint", "")),
                references_bot=False,
                metadata={"source": "recent_loop_decision"},
            )
            self._turn_ledger.mark_completed(identity, metadata={"source": "recent_loop_decision"})

    def _event_timestamp(self, created_at: str) -> float:
        try:
            return datetime.fromisoformat(created_at).timestamp()
        except ValueError:
            return time.time()
