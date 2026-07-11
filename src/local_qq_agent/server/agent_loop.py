from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
import hashlib
import re
import time
from typing import Any, Callable
import unicodedata

from local_qq_agent.agent import LocalAgent
from local_qq_agent.agent.commands import parse_message_commands
from local_qq_agent.agent.engagement import stable_roll
from local_qq_agent.agent.run_log import export_clean_run_log
from local_qq_agent.agent.turns import CleanTurn
from local_qq_agent.config import AutonomyConfig, OneBotConfig
from local_qq_agent.memory import SQLiteMemoryStore
from local_qq_agent.onebot import OneBotGateway, OneBotMessage
from local_qq_agent.paths import project_path
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
class CleanedOneBotTurn:
    raw: OneBotMessage
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
    def source_message_ids(self) -> list[str]:
        value = self.raw.raw_event.get("source_message_ids")
        if isinstance(value, list):
            return [str(item) for item in value]
        return [self.raw.message_id]

    def to_dict(self) -> dict[str, Any]:
        data = self.raw.to_dict()
        data["raw_text"] = self.raw.text
        data["clean_text"] = self.turn.text
        data["clean_identity"] = self.identity
        data["turn_cleaning"] = self.turn.to_metadata()
        return data


@dataclass
class PendingTurnGroup:
    sender_name: str
    messages: list[CleanedOneBotTurn]
    first_seen_at: float
    updated_at: float

    def add(self, message: CleanedOneBotTurn, *, now: float) -> bool:
        if message.fingerprint in self.fingerprints:
            return False
        if message.identity in self.identities:
            return False
        self.messages.append(message)
        self.updated_at = now
        return True

    @property
    def fingerprints(self) -> set[str]:
        return {message.fingerprint for message in self.messages}

    @property
    def identities(self) -> set[str]:
        return {message.identity for message in self.messages}

    def ready(self, *, now: float, quiet_period_seconds: float) -> bool:
        return now - self.updated_at >= max(quiet_period_seconds, 0.0)

    def to_message(self, identity_builder: Callable[[str, str], str]) -> CleanedOneBotTurn:
        latest = self.messages[-1]
        text = "\n".join(message.text for message in self.messages if message.text).strip()
        raw_text = "\n".join(message.raw_text for message in self.messages if message.raw_text).strip()
        fingerprint = self._combined_fingerprint()
        source_message_ids = [
            source_id
            for message in self.messages
            for source_id in message.source_message_ids
        ]
        raw = replace(
            latest.raw,
            text=raw_text or text,
            raw_event={**latest.raw.raw_event, "source_message_ids": source_message_ids},
        )
        removed_lines: list[str] = []
        for message in self.messages:
            removed_lines.extend(message.turn.removed_lines)
        turn = CleanTurn(
            original_text=raw.text,
            text=text,
            removed_lines=tuple(removed_lines),
            reason="quiet_period_merged" if len(self.messages) > 1 else latest.turn.reason,
            references_bot=any(message.references_bot for message in self.messages),
        )
        return CleanedOneBotTurn(
            raw=raw,
            turn=turn,
            identity=f"onebot-batch:{latest.raw.self_id}:{':'.join(source_message_ids)}",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender_name": self.sender_name,
            "message_count": len(self.messages),
            "first_seen_at": round(self.first_seen_at, 3),
            "updated_at": round(self.updated_at, 3),
            "message_text": "\n".join(message.text for message in self.messages if message.text),
            "fingerprints": sorted(self.fingerprints),
        }

    def _combined_fingerprint(self) -> str:
        source = "|".join(sorted(self.fingerprints))
        digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]
        return f"turn-group:{digest}"


class AgentLoop:
    def __init__(
        self,
        *,
        agent: LocalAgent,
        gateway: OneBotGateway,
        store: SQLiteMemoryStore,
        config: OneBotConfig,
        autonomy_config: AutonomyConfig | None = None,
        reboot_scheduler: Callable[[str], dict[str, Any]] | None = None,
        is_active_instance: Callable[[], bool] | None = None,
    ) -> None:
        self.agent = agent
        self.gateway = gateway
        self.store = store
        self.config = config
        self.autonomy_config = autonomy_config or AutonomyConfig.load()
        self.reboot_scheduler = reboot_scheduler
        self.is_active_instance = is_active_instance
        self._task: asyncio.Task[None] | None = None
        self._processor_task: asyncio.Task[None] | None = None
        self._tick_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._transport_wakeup = asyncio.Event()
        self._processor_wakeup = asyncio.Event()
        self._stop_requested = False
        self._context_fingerprints: set[str] = set()
        self._context_turn_ids: set[str] = set()
        self._pending_messages: deque[CleanedOneBotTurn] = deque()
        self._pending_turn_groups: dict[str, PendingTurnGroup] = {}
        self._turn_ledger = TurnLedger(ttl_seconds=config.duplicate_suppression_seconds)
        self._active_message: dict[str, Any] | None = None
        self._sent_texts: list[str] = []
        self._manual_force_lock = asyncio.Lock()
        self._manual_force_inflight: set[str] = set()
        self._manual_force_recent: dict[str, tuple[float, dict[str, Any]]] = {}
        self._decisions: list[LoopDecision] = []
        self._next_read_allowed_at = 0.0
        self._idle_read_ticks = 0
        self._last_scrollback_context_at = 0.0
        self._last_non_bot_message_at = time.time()
        self._last_bot_message_at = 0.0
        self._spontaneous_tokens = float(self.autonomy_config.spontaneous_token_capacity)
        self._spontaneous_tokens_updated_at = time.time()
        self._spontaneous_backoff_until = 0.0
        self._spontaneous_status: dict[str, Any] = {"enabled": self.autonomy_config.allow_spontaneous_topics}
        self._activity = self._activity_state(stage="idle", detail="Loop is not running.")
        self._session_start_event_id: int | None = None
        self._inactive_instance_recorded = False
        self._hydrate_processed_messages()
        self.gateway.add_message_listener(self.ingest_message)

    def remember_sent_text(self, text: str) -> None:
        outgoing = text.strip()
        if not outgoing:
            return
        self._sent_texts.append(outgoing)
        self._sent_texts = self._sent_texts[-20:]

    def status(self) -> dict[str, Any]:
        task_done = self._task.done() if self._task else True
        processor_done = self._processor_task.done() if self._processor_task else True
        ledger_summary = self._turn_ledger.summary()
        return {
            "running": self.running,
            "task_done": task_done,
            "processor_running": self._processor_task is not None and not processor_done,
            "processor_done": processor_done,
            "transport": "onebot11_reverse_websocket",
            "onebot": self.gateway.status().to_dict(),
            "duplicate_suppression_seconds": self.config.duplicate_suppression_seconds,
            "turn_quiet_period_seconds": self.config.turn_quiet_period_seconds,
            "startup_scrollback_readable_messages": self.config.startup_scrollback_readable_messages,
            "max_messages_per_tick": self.config.max_messages_per_tick,
            "ignore_existing_on_start": self.config.ignore_existing_on_start,
            "target_sender_name": self.config.target_sender_name,
            "target_group_id": self.gateway.status().target_group_id,
            "expected_group_name": self.gateway.status().target_group_name,
            "context_seen_count": len(self._context_fingerprints),
            "aggregating_message_count": len(self._pending_turn_groups),
            "pending_message_count": len(self._pending_messages),
            "queued_message_count": len(self._turn_ledger.active_ids("queued")),
            "inflight_message_count": len(self._turn_ledger.active_ids("inflight")),
            "placeholder_seen_count": ledger_summary["response_counts"]["wait_attempted"],
            "ledger": ledger_summary,
            "spontaneous": dict(self._spontaneous_status),
            "active_message": dict(self._active_message) if self._active_message else None,
            "pending_messages": [self._message_status(message) for message in list(self._pending_messages)[:20]],
            "inflight_message_ids": self._turn_ledger.active_ids("inflight"),
            "tick_busy": self._tick_lock.locked(),
            "stop_requested": self._stop_requested,
            "active_instance": self._is_active_instance(),
            "activity": dict(self._activity),
            "aggregating_messages": [group.to_dict() for group in self._pending_turn_groups.values()],
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
                    content="OneBot loop stopped because another agent instance is active",
                    metadata={"source_stage": stage, "status": self.status()},
                )
        return {"ok": False, "reason": "inactive_agent_instance", "source_stage": stage}

    def _next_poll_interval(self) -> float:
        return 0.5

    async def start(self) -> dict[str, Any]:
        if self.running:
            return self.status()
        if not self._is_active_instance():
            self._stop_for_inactive_instance("start")
            return self.status()

        self._stop_requested = False
        self._clear_pending_messages()
        baseline: dict[str, Any] | None = None
        if self.config.ignore_existing_on_start:
            self._set_activity(stage="baseline_reading", detail="Loading OneBot group history as startup context.")
            baseline = await self._mark_startup_baseline()
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
                    content=f"OneBot agent loop start blocked: {baseline.get('reason', 'baseline_failed')}",
                    metadata={"baseline": baseline, "status": self.status()},
                )
                return self.status()

        self._task = asyncio.create_task(self._run(), name="onebot-agent-loop")
        self._ensure_processor_running("start")
        self._set_activity(stage="running_idle", detail="Loop started. Waiting for new target messages.")
        start_event = self.store.append_event(
            source="loop",
            kind="loop_started",
            content="OneBot agent loop started",
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
        self._transport_wakeup.set()
        self._processor_wakeup.set()
        self._set_activity(stage="stopping", detail="Stop requested. Waiting for current tick to finish.")
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=6.0)
        except TimeoutError:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._processor_task is not None and not self._processor_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._processor_task), timeout=6.0)
            except TimeoutError:
                self._processor_task.cancel()
                try:
                    await self._processor_task
                except asyncio.CancelledError:
                    pass

        self.store.append_event(
            source="loop",
            kind="loop_stopped",
            content="OneBot agent loop stopped",
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

        async with self._tick_lock:
            ready = self._flush_ready_turn_groups(now=time.time())
            queued = [item for item in (self._queue_cleaned_message(message) for message in ready) if item]
            if queued:
                self._processor_wakeup.set()
            spontaneous = None
            if not self._pending_messages and not self._pending_turn_groups:
                spontaneous = await self._maybe_send_spontaneous(started_at=time.perf_counter())
            self._set_activity(
                stage="running_idle",
                detail="Waiting for OneBot events." if not queued else "Queued OneBot turns are waiting.",
            )
            return {
                "ok": True,
                "reason": "event_queue_checked",
                "flushed": [message.to_dict() for message in queued],
                "pending_message_count": len(self._pending_messages),
                "aggregating_message_count": len(self._pending_turn_groups),
                "spontaneous": spontaneous,
            }

    async def ingest_message(self, message: OneBotMessage) -> None:
        """Persist a OneBot event once, then route only target-group human messages."""
        target_group_id = self.gateway.status().target_group_id
        state = "observed"
        if message.group_id != target_group_id:
            state = "wrong_group"
        elif message.is_self:
            state = "bot_echo"
        inserted = self.store.observe_transport_turn(
            canonical_turn_id=message.canonical_turn_id,
            message_id=message.message_id,
            self_id=message.self_id,
            group_id=message.group_id,
            user_id=message.user_id,
            sender_name=message.sender_name,
            message_text=message.text,
            state=state,
            metadata={"source": message.source, "segments": list(message.segments)},
        )
        if not inserted:
            self.store.append_event(
                source="onebot",
                kind="duplicate_event_suppressed",
                content=f"Duplicate OneBot message suppressed: {message.message_id}",
                metadata={"canonical_turn_id": message.canonical_turn_id, "message_id": message.message_id},
            )
            return
        if message.group_id != target_group_id:
            self.store.update_transport_turn(message.canonical_turn_id, state="wrong_group")
            return
        if message.is_self:
            self.store.update_transport_turn(message.canonical_turn_id, state="bot_echo")
            self.remember_sent_text(message.text)
            return
        if not message.text:
            self.store.update_transport_turn(message.canonical_turn_id, state="context_only")
            return

        affinity = 1.0 if self._same_sender(message.sender_name, self.config.target_sender_name) else 0.5
        contact = self.agent.social_state.ensure_contact(
            user_name=message.sender_name,
            user_id=message.user_id,
            aliases=(message.sender_name,),
            initial_affinity=affinity,
            source="onebot_sender",
        )
        if contact.user_name != message.sender_name:
            message = replace(message, sender_name=contact.user_name)
        cleaned = self._clean_message(message)
        self._record_context_message(cleaned, agent_reason="onebot_event", agent_action="observed")
        if not self.running:
            self.store.update_transport_turn(
                message.canonical_turn_id,
                state="context_only",
                metadata={"reason": "loop_stopped"},
            )
            return

        sender_key = self._stable_text(cleaned.sender_name)
        ready: list[CleanedOneBotTurn] = []
        for key, group in list(self._pending_turn_groups.items()):
            if key == sender_key:
                continue
            ready.append(group.to_message(self._message_identity))
            self._pending_turn_groups.pop(key, None)
        for pending in ready:
            self._queue_cleaned_message(pending)
        self._enqueue_messages([message], respect_quiet_period=True, now=time.time())
        self._last_non_bot_message_at = time.time()
        self._transport_wakeup.set()

    def _record_history_context(self, message: OneBotMessage) -> bool:
        state = "bot_echo" if message.is_self else "context_only"
        inserted = self.store.observe_transport_turn(
            canonical_turn_id=message.canonical_turn_id,
            message_id=message.message_id,
            self_id=message.self_id,
            group_id=message.group_id,
            user_id=message.user_id,
            sender_name=message.sender_name,
            message_text=message.text,
            state=state,
            metadata={"source": "history"},
        )
        if not inserted or message.is_self or not message.text:
            return inserted
        cleaned = self._clean_message(message)
        self._record_context_message(cleaned, agent_reason="startup_history", agent_action="context_only")
        return True

    async def collect_scrollback(self, *, pages: int = 3) -> dict[str, Any]:
        messages = await self.gateway.history(count=max(1, min(pages * 30, 100)))
        recorded = sum(1 for message in messages if self._record_history_context(message))
        return {
            "ok": True,
            "reason": "onebot_history_collected",
            "message_count": len(messages),
            "recorded": recorded,
        }

    async def _maybe_send_spontaneous(self, *, started_at: float) -> dict[str, Any] | None:
        now = time.time()
        preflight = self._spontaneous_preflight(now)
        self._spontaneous_status = preflight
        if not preflight["eligible"]:
            return None

        target_per_hour = float(preflight["target_per_hour"])
        probability = self.agent.engagement_policy.spontaneous_probability(
            target_per_hour=target_per_hour,
            interval_seconds=self._next_poll_interval(),
        )
        roll = stable_roll(f"spontaneous|{int(now // max(self._next_poll_interval(), 1.0))}|{self._session_start_event_id}")
        self._spontaneous_status = {**preflight, "probability": probability, "roll": round(roll, 4)}
        if roll >= probability:
            return None

        self._set_activity(
            stage="spontaneous_generating",
            detail="Generating an idle spontaneous topic.",
            metadata=self._spontaneous_status,
        )
        message = (
            "Generate one short spontaneous QQ group message based on recent context, current mood, and relationship state. "
            "Do not explain that you are starting a topic. Do not mention debug state. .enforce .think 3"
        )
        result = await self.agent.respond_to_incoming(
            user_name="spontaneous_topic",
            message=message,
            record_incoming_event=False,
        )

        sent = False
        send_reason = "not_sent"
        send_result: dict[str, Any] | None = None
        topic_check = self._spontaneous_topic_check(result.reply)
        if result.action == "reply" and result.reply and topic_check["ok"]:
            async with self._send_lock:
                send_result = await self._send_unquoted_text_unlocked(
                    text=result.reply,
                    stage="spontaneous_topic",
                    mode="spontaneous_unquoted",
                )
            sent = bool(send_result.get("sent"))
            send_reason = str(send_result.get("reason", "unknown"))
            if sent:
                self._spontaneous_tokens = max(0.0, self._spontaneous_tokens - 1.0)
                self._last_bot_message_at = time.time()
                self._sent_texts.append(result.reply)
                self._sent_texts = self._sent_texts[-20:]
            else:
                self._spontaneous_backoff_until = time.time() + self.autonomy_config.spontaneous_backoff_seconds
        else:
            self._spontaneous_backoff_until = time.time() + self.autonomy_config.spontaneous_backoff_seconds

        decision = LoopDecision(
            created_at=time.time(),
            message_text="spontaneous_topic",
            sender_name="agent",
            action=result.action,
            reason=f"spontaneous_{result.reason}",
            sent=sent,
            send_reason=send_reason,
            elapsed_seconds=round(time.perf_counter() - started_at, 3),
            metadata={
                **result.metadata,
                "send_result": send_result,
                "spontaneous": self._spontaneous_status,
                "spontaneous_topic_check": topic_check,
            },
        )
        self._remember_decision(decision)
        self._set_activity(
            stage="spontaneous_sent" if sent else "spontaneous_skipped",
            detail="Spontaneous topic finished.",
            metadata=asdict(decision),
        )
        return self._decision_status(decision)

    def _spontaneous_preflight(self, now: float) -> dict[str, Any]:
        self._refresh_spontaneous_tokens(now)
        idle_seconds = max(0.0, now - self._last_non_bot_message_at)
        bot_idle_seconds = max(0.0, now - self._last_bot_message_at) if self._last_bot_message_at else 999999.0
        social_state = getattr(self.agent, "social_state", None)
        global_state_getter = getattr(social_state, "global_state", None)
        global_state = global_state_getter() if callable(global_state_getter) else {}
        engagement_policy = getattr(self.agent, "engagement_policy", None)
        agent_settings = getattr(self.agent, "settings", None)
        activity = float(getattr(agent_settings, "activity", 0.0))
        target_per_hour = (
            engagement_policy.spontaneous_target_per_hour(
                activity=activity,
                global_affinity=float(global_state.get("global_affinity", 0.5)),
                mood_label=str(global_state.get("global_mood", "neutral")),
                mood_intensity=float(global_state.get("mood_intensity", 0.0)),
                context_interest=self._spontaneous_context_interest(),
            )
            if engagement_policy is not None
            else 0.0
        )
        status = {
            "enabled": self.autonomy_config.allow_spontaneous_topics,
            "eligible": False,
            "reason": "",
            "tokens": round(self._spontaneous_tokens, 3),
            "target_per_hour": target_per_hour,
            "idle_seconds": round(idle_seconds, 1),
            "bot_idle_seconds": round(bot_idle_seconds, 1),
            "backoff_until": round(self._spontaneous_backoff_until, 3),
        }
        if not self.autonomy_config.allow_spontaneous_topics:
            return {**status, "reason": "disabled"}
        if self.autonomy_config.require_human_trigger_for_demo:
            return {**status, "reason": "manual_trigger_required"}
        if activity <= 0:
            return {**status, "reason": "activity_zero"}
        if self._pending_messages or self._active_message:
            return {**status, "reason": "queue_not_empty"}
        if now < self._spontaneous_backoff_until:
            return {**status, "reason": "backoff"}
        if self._spontaneous_tokens < 1.0:
            return {**status, "reason": "bucket_empty"}
        if idle_seconds < self.autonomy_config.spontaneous_min_idle_seconds:
            return {**status, "reason": "group_not_idle"}
        if bot_idle_seconds < self.autonomy_config.spontaneous_bot_cooldown_seconds:
            return {**status, "reason": "bot_cooldown"}
        if target_per_hour <= 0:
            return {**status, "reason": "target_zero"}
        return {**status, "eligible": True, "reason": "eligible"}

    def _refresh_spontaneous_tokens(self, now: float) -> None:
        elapsed = max(0.0, now - self._spontaneous_tokens_updated_at)
        refill = elapsed * self.autonomy_config.spontaneous_token_refill_per_hour / 3600.0
        capacity = max(0.0, self.autonomy_config.spontaneous_token_capacity)
        self._spontaneous_tokens = min(capacity, self._spontaneous_tokens + refill)
        self._spontaneous_tokens_updated_at = now

    def _spontaneous_context_interest(self) -> float:
        if self._decisions and self._decisions[-1].action == "no_reply":
            return 0.7
        if self._context_fingerprints:
            return 0.6
        return 0.45

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
                    content="OneBot agent loop event flush failed",
                    metadata={"error": str(error)},
                )
            if self._stop_requested:
                break
            try:
                await asyncio.wait_for(self._transport_wakeup.wait(), timeout=0.5)
                self._transport_wakeup.clear()
            except TimeoutError:
                pass

    async def _process_pending_messages(self) -> None:
        while not self._stop_requested:
            if not self._is_active_instance():
                self._stop_for_inactive_instance("processor")
                break
            if not self._pending_messages:
                self._processor_wakeup.clear()
                try:
                    await asyncio.wait_for(self._processor_wakeup.wait(), timeout=0.5)
                except TimeoutError:
                    continue
                continue

            processed = await self._process_next_pending_message()
            if not processed:
                await asyncio.sleep(0.2)

    def _ensure_processor_running(self, reason: str) -> None:
        if self._stop_requested:
            return
        if not self._is_active_instance():
            self._stop_for_inactive_instance(f"processor_restart_{reason}")
            return
        if self._processor_task is not None and not self._processor_task.done():
            return

        self._processor_task = asyncio.create_task(self._process_pending_messages(), name="onebot-agent-processor")
        self._processor_task.add_done_callback(self._record_processor_exit)
        if self.store is not None:
            self.store.append_event(
                source="loop",
                kind="loop_processor_started",
                content="OneBot pending-message processor started",
                metadata={"reason": reason, "pending_message_count": len(self._pending_messages)},
            )

    def _record_processor_exit(self, task: asyncio.Task[None]) -> None:
        if task.cancelled() or self._stop_requested:
            return

        try:
            error = task.exception()
        except asyncio.CancelledError:
            return

        if error is None:
            if self.store is not None:
                self.store.append_event(
                    source="loop",
                    kind="loop_processor_stopped",
                    content="OneBot pending-message processor stopped unexpectedly",
                    metadata={"pending_message_count": len(self._pending_messages)},
                )
            return

        if self.store is not None:
            self.store.append_event(
                source="loop",
                kind="loop_processor_error",
                content="OneBot pending-message processor failed",
                metadata={
                    "error": repr(error),
                    "pending_message_count": len(self._pending_messages),
                    "active_message": self._active_message,
                },
            )

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
            if self._message_seen(message.sender_name, message.text, message.fingerprint):
                continue

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
                self._active_message = None

        return None

    async def _handle_message(self, message: CleanedOneBotTurn | OneBotMessage, started_at: float) -> LoopDecision:
        if not isinstance(message, CleanedOneBotTurn):
            message = self._clean_message(message)
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
            record_incoming_event=False,
            turn_identity=message.identity,
        )
        result = self._with_loop_command_feedback(result)
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
                "token_usage": result.metadata.get("token_usage"),
                "engagement_decision": result.metadata.get("engagement_decision"),
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

        if result.metadata.get("spontaneous_requested"):
            return await self._handle_spontaneous_command(message=message, result=result, started_at=started_at)

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
            if not self._turn_ledger.can_send_answer(message.identity, message.fingerprint):
                decision = LoopDecision(
                    created_at=time.time(),
                    message_text=text,
                    sender_name=sender_name,
                    action="skip",
                    reason="answer_already_attempted_for_message",
                    sent=False,
                    send_reason="answer_already_attempted_for_message",
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
                    stage="send_blocked",
                    detail="Final answer was already attempted for this message.",
                    sender_name=sender_name,
                    message_text=text,
                    metadata=asdict(decision),
                )
                return decision

            self._set_activity(
                stage="sending",
                detail="Sending reply through OneBot.",
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
            self._turn_ledger.mark_answer_result(
                message.identity,
                sent=sent,
                result=send_result,
                text=outgoing,
            )
            if sent:
                self._sent_texts.append(outgoing)
                self._sent_texts = self._sent_texts[-20:]
                self._last_bot_message_at = time.time()
            if sent and result.metadata.get("reboot_requested"):
                result.metadata["reboot_schedule"] = self._schedule_reboot("qq_command")
            if result.metadata.get("loop_command_requested") == "stop":
                self._stop_requested = True
                self._processor_wakeup.set()
                result.metadata["loop_stop_requested_after_feedback"] = True
        elif self._should_send_debug_no_reply_notice(message, result):
            notice = self._debug_no_reply_notice(result)
            send_result = await self._send_quoted_text(
                message=message,
                text=notice,
                stage="debug_no_reply_reason",
                allow_unquoted_fallback=True,
            )
            sent = bool(send_result.get("sent"))
            send_reason = str(send_result.get("reason", "unknown"))
            if sent:
                self._sent_texts.append(notice)
                self._sent_texts = self._sent_texts[-20:]
                self._last_bot_message_at = time.time()
            result.metadata["debug_no_reply_notice"] = notice

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
        self._persist_transport_decision(message, decision)
        self._remember_seen_message(sender_name, text, message.fingerprint)
        if decision.action == "no_reply":
            stage = "no_reply"
            detail = "Agent decided not to reply."
        elif decision.sent:
            stage = "sent"
            detail = "Reply sent through OneBot."
        elif decision.send_reason != "not_sent":
            stage = "send_blocked"
            detail = f"OneBot send did not execute: {decision.send_reason}."
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

    async def _handle_spontaneous_command(
        self,
        *,
        message: CleanedOneBotTurn,
        result,
        started_at: float,
    ) -> LoopDecision:
        self._set_activity(
            stage="spontaneous_command_generating",
            detail="Generating a manually requested spontaneous topic.",
            sender_name=message.sender_name,
            message_text=message.text,
            metadata={"command_message_identity": message.identity},
        )
        prompt = (
            "Generate one short spontaneous QQ group message based on recent context, current mood, and relationship state. "
            "Do not explain that you are starting a topic. Do not mention debug state. .enforce .think 3"
        )
        topic_result = await self.agent.respond_to_incoming(
            user_name=message.sender_name,
            message=prompt,
            record_incoming_event=False,
            turn_identity=f"{message.identity}|spontaneous-command",
        )

        sent = False
        send_reason = "not_sent"
        send_result: dict[str, Any] | None = None
        topic_check = self._spontaneous_topic_check(topic_result.reply)
        if topic_result.action == "reply" and topic_result.reply and topic_check["ok"]:
            async with self._send_lock:
                send_result = await self._send_unquoted_text_unlocked(
                    text=topic_result.reply,
                    stage="spontaneous_command",
                    mode="spontaneous_command_unquoted",
                )
            sent = bool(send_result.get("sent"))
            send_reason = str(send_result.get("reason", "unknown"))
            if sent:
                self._sent_texts.append(topic_result.reply)
                self._sent_texts = self._sent_texts[-20:]
                self._last_bot_message_at = time.time()

        metadata = {
            **result.metadata,
            "command_result": result.to_dict(),
            "spontaneous_result": topic_result.to_dict(),
            "spontaneous_topic_check": topic_check,
            "send_result": send_result,
            "message_identity": message.identity,
            "source_fingerprint": message.fingerprint,
            "raw_message_text": message.raw_text,
            "loop_turn_cleaning": message.turn.to_metadata(),
        }
        decision = LoopDecision(
            created_at=time.time(),
            message_text=message.text,
            sender_name=message.sender_name,
            action=topic_result.action,
            reason=f"spontaneous_command_{topic_result.reason}",
            sent=sent,
            send_reason=send_reason,
            elapsed_seconds=round(time.perf_counter() - started_at, 3),
            metadata=metadata,
        )
        self._remember_decision(decision)
        self._remember_seen_message(message.sender_name, message.text, message.fingerprint)
        self._set_activity(
            stage="spontaneous_command_sent" if sent else "spontaneous_command_done",
            detail="Manual spontaneous command finished.",
            sender_name=message.sender_name,
            message_text=message.text,
            metadata=asdict(decision),
        )
        return decision

    def _persist_transport_decision(self, message: CleanedOneBotTurn, decision: LoopDecision) -> None:
        send_result = decision.metadata.get("send_result") or {}
        metadata = {
            "decision_action": decision.action,
            "decision_reason": decision.reason,
            "sent": decision.sent,
            "send_reason": decision.send_reason,
            "outbound_message_id": str(send_result.get("message_id", "")),
            "source_message_ids": message.source_message_ids,
        }
        if str(send_result.get("state", "")) == "unknown":
            state = "send_unknown"
        elif decision.action == "no_reply":
            state = "context_only"
        else:
            state = "completed"
        for source_id in message.source_message_ids:
            canonical_id = f"onebot:{message.raw.self_id}:{source_id}"
            self.store.update_transport_turn(canonical_id, state=state, metadata=metadata)

    def _spontaneous_topic_check(self, reply: str) -> dict[str, Any]:
        text = reply.strip()
        key = self._spontaneous_semantic_key(text)
        has_question = "?" in text or "？" in text
        has_clause = bool(re.search(r"[,，、。]\s*\S", text))

        if not text:
            return {"ok": False, "reason": "empty_spontaneous_reply"}
        if self._looks_like_idle_weather_report(key, text) and not has_question and not has_clause:
            return {"ok": False, "reason": "low_value_idle_observation", "semantic_length": len(key)}
        if len(key) < 8 and not has_question:
            return {"ok": False, "reason": "too_short_for_spontaneous_topic", "semantic_length": len(key)}
        return {"ok": True, "reason": "topic_has_value", "semantic_length": len(key)}

    def _spontaneous_semantic_key(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text.casefold())
        return "".join(char for char in normalized if char.isalnum() or "\u4e00" <= char <= "\u9fff")

    def _looks_like_idle_weather_report(self, key: str, text: str) -> bool:
        low_value_keys = {
            "\u4eca\u5929\u633a\u5b89\u9759\u7684",
            "\u4eca\u5929\u590f\u81f3\u554a",
            "\u4eca\u5929\u7236\u4eb2\u8282\u554a",
        }
        if key in low_value_keys:
            return True
        if key.startswith("\u4eca\u5929") and len(key) <= 8:
            return True
        if re.fullmatch(
            r"[\.\u3002\u2026\s]*(\u4eca\u5929|\u73b0\u5728|\u7fa4\u91cc).*(\u5b89\u9759|\u6ca1\u4eba|\u590f\u81f3|\u7236\u4eb2\u8282)[\.\u3002\u2026\s]*",
            text,
        ):
            return True
        if key in {"今天挺安静的", "今天夏至啊", "今天父亲节啊"}:
            return True
        if key.startswith("今天") and len(key) <= 8:
            return True
        return bool(re.fullmatch(r"[.。…\s]*(今天|现在|群里).*(安静|没人|夏至|父亲节)[.。…\s]*", text))

    async def force_reply(
        self,
        *,
        sender_name: str,
        message_text: str,
        event_id: int | None = None,
        extra_instruction: str = "",
        send_to_qq: bool = True,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        sender_name = sender_name.strip() or self.config.target_sender_name or "debug_user"
        message_text = message_text.strip()
        if not message_text:
            raise ValueError("message_text must not be empty")

        force_key = self._manual_force_key(
            sender_name=sender_name,
            message_text=message_text,
            event_id=event_id,
        )
        duplicate = await self._begin_manual_force(force_key)
        if duplicate is not None:
            return duplicate

        self._set_activity(
            stage="manual_force_running",
            detail="Manual force reply is running.",
            sender_name=sender_name,
            message_text=message_text,
            metadata={"event_id": event_id, "send_to_qq": send_to_qq},
        )
        try:
            turn_identity = f"manual-force|{event_id or self._message_identity(sender_name, message_text)}"
            result = await self.agent.respond_to_incoming(
                user_name=sender_name,
                message=f"{message_text} .enforce .think 3",
                external_context=extra_instruction.strip(),
                reply_to_bot=True,
                record_incoming_event=False,
                turn_identity=turn_identity,
            )

            sent = False
            send_reason = "not_requested" if not send_to_qq else "not_sent"
            send_result: dict[str, Any] | None = None
            if send_to_qq and result.action == "reply" and result.reply:
                try:
                    send_preflight = self._send_preflight()
                    if not send_preflight["ok"]:
                        send_reason = str(send_preflight.get("reason", "send_blocked"))
                        send_result = send_preflight
                    else:
                        target = await self._ledger_quote_target_for(sender_name=sender_name, message_text=message_text)
                        if target is not None:
                            send_result = await self._send_quoted_text(
                                message=target,
                                text=result.reply,
                                stage="manual_force_reply",
                                allow_unquoted_fallback=True,
                            )
                        else:
                            async with self._send_lock:
                                send_result = await self._send_unquoted_text_unlocked(
                                    text=result.reply,
                                    stage="manual_force_reply",
                                    mode="manual_unquoted_no_ledger_target",
                                )
                    if send_result is not None:
                        sent = bool(send_result.get("sent"))
                        send_reason = str(send_result.get("reason", "unknown"))
                except Exception as error:
                    send_result = self._send_exception_result(
                        text=result.reply,
                        stage="manual_force_reply",
                        mode="manual_force",
                        error=error,
                    )
                    sent = False
                    send_reason = str(send_result["reason"])
                if sent:
                    self.remember_sent_text(result.reply)
                    self._last_bot_message_at = time.time()

            decision = LoopDecision(
                created_at=time.time(),
                message_text=message_text,
                sender_name=sender_name,
                action=result.action,
                reason=f"manual_force_{result.reason}",
                sent=sent,
                send_reason=send_reason,
                elapsed_seconds=round(time.perf_counter() - started_at, 3),
                metadata={
                    **result.metadata,
                    "agent_reply": result.reply,
                    "manual_force": True,
                    "manual_event_id": event_id,
                    "manual_force_key": force_key,
                    "send_result": send_result,
                },
            )
            self._remember_decision(decision)
            self._set_activity(
                stage="manual_force_sent" if sent else "manual_force_done",
                detail="Manual force reply finished.",
                sender_name=sender_name,
                message_text=message_text,
                metadata=asdict(decision),
            )
            status = self._decision_status(decision)
            await self._finish_manual_force(force_key, status)
            return status
        except Exception:
            await self._finish_manual_force(force_key, None)
            raise

    def _manual_force_key(self, *, sender_name: str, message_text: str, event_id: int | None) -> str:
        if event_id is not None:
            return f"event:{event_id}"
        return self._message_identity(sender_name, message_text)

    async def _begin_manual_force(self, force_key: str) -> dict[str, Any] | None:
        async with self._manual_force_lock:
            self._prune_manual_force_recent()
            if force_key in self._manual_force_inflight:
                return {
                    "state": "ignored",
                    "operation": "manual_force_reply",
                    "reason": "manual_force_already_inflight",
                    "manual_force_key": force_key,
                    "sent": False,
                }
            recent = self._manual_force_recent.get(force_key)
            if recent is not None:
                cached = dict(recent[1])
                cached["duplicate"] = True
                cached["reason"] = "manual_force_recent_duplicate"
                cached["sent"] = False
                cached["send_reason"] = "duplicate_suppressed"
                return cached
            self._manual_force_inflight.add(force_key)
            return None

    async def _finish_manual_force(self, force_key: str, status: dict[str, Any] | None) -> None:
        async with self._manual_force_lock:
            self._manual_force_inflight.discard(force_key)
            if status is not None:
                self._manual_force_recent[force_key] = (time.time(), dict(status))
            self._prune_manual_force_recent()

    def _prune_manual_force_recent(self) -> None:
        cutoff = time.time() - min(max(self.config.duplicate_suppression_seconds, 30.0), 300.0)
        stale = [key for key, (created_at, _) in self._manual_force_recent.items() if created_at < cutoff]
        for key in stale:
            self._manual_force_recent.pop(key, None)

    async def _ledger_quote_target_for(self, *, sender_name: str, message_text: str) -> CleanedOneBotTurn | None:
        expected_sender = self._stable_text(sender_name)
        expected_text = self._stable_text(message_text)
        for row in self.store.recent_transport_turns(limit=200):
            if self._stable_text(str(row["sender_name"])) != expected_sender:
                continue
            if self._stable_text(str(row["message_text"])) != expected_text:
                continue
            message = OneBotMessage(
                message_id=str(row["message_id"]),
                self_id=str(row["self_id"]),
                group_id=str(row["group_id"]),
                user_id=str(row["user_id"]),
                sender_name=str(row["sender_name"]),
                text=str(row["message_text"]),
                timestamp=int(time.time()),
                source="ledger",
            )
            return self._clean_message(message)
        return None

    async def _send_placeholder(self, *, message: CleanedOneBotTurn | OneBotMessage, placeholder: str) -> dict[str, Any]:
        if not self._is_active_instance():
            self._stop_for_inactive_instance("placeholder")
            return {"sent": False, "reason": "inactive_agent_instance"}
        if self._stop_requested:
            return {"sent": False, "reason": "loop_stopped_before_placeholder"}

        cleaned = message if isinstance(message, CleanedOneBotTurn) else self._clean_message(message)
        if not self._turn_ledger.can_send_wait(cleaned.identity, cleaned.fingerprint):
            return {
                "sent": False,
                "reason": "placeholder_already_sent_for_message",
                "message_identity": cleaned.identity,
            }
        self._turn_ledger.mark_wait_attempted(
            cleaned.identity,
            text=placeholder,
            metadata={"fingerprint": cleaned.fingerprint, "raw_message_text": cleaned.raw_text},
        )

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
        self._turn_ledger.mark_wait_result(cleaned.identity, sent=bool(result.get("sent")), result=result)
        if result.get("sent"):
            self._sent_texts.append(placeholder)
            self._sent_texts = self._sent_texts[-20:]
            self._last_bot_message_at = time.time()
        return result

    async def _send_quoted_text(
        self,
        *,
        message: CleanedOneBotTurn | OneBotMessage,
        text: str,
        stage: str,
        quote_reply: bool = True,
        allow_unquoted_fallback: bool = False,
    ) -> dict[str, Any]:
        async with self._send_lock:
            if not quote_reply:
                return await self._send_unquoted_text_unlocked(text=text, stage=stage, mode="followup_unquoted")

            target, quote_refresh = await self._fresh_quote_target_unlocked(message)

            try:
                send_result = await self.gateway.send_text(text, reply_to=target)
                result = send_result.to_dict()
            except Exception as error:
                result = self._send_exception_result(
                    text=text,
                    stage=stage,
                    mode="quote_reply",
                    error=error,
                )
            verification = result.setdefault("verification", {})
            if isinstance(verification, dict):
                verification["quote_refresh"] = quote_refresh
                verification["stage"] = stage
            return result

    async def _send_unquoted_text_unlocked(self, *, text: str, stage: str, mode: str) -> dict[str, Any]:
        try:
            send_result = await self.gateway.send_text(text, reply_to=None)
            result = send_result.to_dict()
        except Exception as error:
            result = self._send_exception_result(text=text, stage=stage, mode=mode, error=error)
        verification = result.setdefault("verification", {})
        if isinstance(verification, dict):
            verification["stage"] = stage
            verification["mode"] = mode
        return result

    def _send_exception_result(self, *, text: str, stage: str, mode: str, error: Exception) -> dict[str, Any]:
        return {
            "sent": False,
            "reason": "send_error",
            "text": text,
            "verification": {
                "stage": stage,
                "mode": mode,
                "error": repr(error),
            },
            "duration_seconds": 0.0,
        }

    async def _fresh_quote_target_unlocked(self, message: CleanedOneBotTurn | OneBotMessage) -> tuple[OneBotMessage | None, dict[str, Any]]:
        original = message if isinstance(message, CleanedOneBotTurn) else self._clean_message(message)
        return original.raw, {
            "ok": True,
            "reason": "onebot_message_id",
            "message_id": original.raw.message_id,
            "source_message_ids": original.source_message_ids,
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

    async def _mark_startup_baseline(self) -> dict[str, Any]:
        started_at = time.perf_counter()
        limit = max(1, self.config.startup_scrollback_readable_messages)
        status = self.gateway.status()
        if not status.ready:
            return {"ok": False, "reason": "onebot_not_ready", "onebot": status.to_dict()}
        try:
            messages = await self.gateway.history(count=limit)
        except Exception as error:
            return {
                "ok": False,
                "reason": "history_failed",
                "error": str(error),
            }
        marked = sum(1 for message in messages if self._record_history_context(message))

        return {
            "ok": True,
            "reason": "startup_history_marked",
            "marked_count": marked,
            "history_message_count": len(messages),
            "elapsed_seconds": round(time.perf_counter() - started_at, 3),
            "target_group_id": status.target_group_id,
            "target_group_name": status.target_group_name,
        }

    def _enqueue_messages(
        self,
        messages: list[OneBotMessage],
        *,
        respect_quiet_period: bool = False,
        now: float | None = None,
    ) -> list[CleanedOneBotTurn]:
        enqueued: list[CleanedOneBotTurn] = []
        current_time = time.time() if now is None else now
        for cleaned in self._clean_messages(messages):
            if not cleaned.text:
                self._remember_seen_message(cleaned.sender_name, cleaned.text, cleaned.fingerprint)
                continue
            if self._message_seen(cleaned.sender_name, cleaned.text, cleaned.fingerprint):
                continue
            if self._message_queued(cleaned):
                continue
            if not self._debug_mode_allows_sender(cleaned.sender_name):
                self._record_context_message(
                    cleaned,
                    agent_reason="debug_mode_target_only",
                    agent_action="context_only",
                )
                continue

            if respect_quiet_period and not self._should_enqueue_immediately(cleaned):
                if self._buffer_message(cleaned, now=current_time):
                    self._record_context_message(cleaned, agent_reason="aggregating_turn", agent_action="aggregating")
                continue

            queued = self._queue_cleaned_message(cleaned)
            if queued is not None:
                enqueued.append(queued)

        if respect_quiet_period:
            for ready in self._flush_ready_turn_groups(now=current_time):
                queued = self._queue_cleaned_message(ready)
                if queued is not None:
                    enqueued.append(queued)

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

    def _queue_cleaned_message(self, message: CleanedOneBotTurn) -> CleanedOneBotTurn | None:
        if self._message_queued(message):
            return None
        self._pending_messages.append(message)
        self._turn_ledger.mark_queued(
            message.identity,
            metadata={"fingerprint": message.fingerprint, "raw_message_text": message.raw_text},
        )
        self._record_context_message(message, agent_reason="queued_for_decision", agent_action="queued")
        return message

    def _buffer_message(self, message: CleanedOneBotTurn, *, now: float) -> bool:
        key = self._stable_text(message.sender_name)
        group = self._pending_turn_groups.get(key)
        if group is None:
            self._pending_turn_groups[key] = PendingTurnGroup(
                sender_name=message.sender_name,
                messages=[message],
                first_seen_at=now,
                updated_at=now,
            )
            return True
        return group.add(message, now=now)

    def _flush_ready_turn_groups(self, *, now: float) -> list[CleanedOneBotTurn]:
        ready: list[CleanedOneBotTurn] = []
        quiet_period = self.config.turn_quiet_period_seconds
        for key, group in list(self._pending_turn_groups.items()):
            if not group.ready(now=now, quiet_period_seconds=quiet_period):
                continue
            message = group.to_message(self._message_identity)
            self._pending_turn_groups.pop(key, None)
            self._turn_ledger.observe(
                turn_id=message.identity,
                sender=message.sender_name,
                clean_text=message.text,
                raw_text=message.raw_text,
                fingerprint=message.fingerprint,
                references_bot=message.references_bot,
                metadata={"source": "quiet_period_merge", "message_count": len(group.messages)},
            )
            for fingerprint in group.fingerprints:
                self._turn_ledger.add_alias(message.identity, fingerprint)
            ready.append(message)
        return ready

    def _should_enqueue_immediately(self, message: CleanedOneBotTurn) -> bool:
        text = message.text.strip()
        parsed = parse_message_commands(text)
        if parsed.command_suffixes:
            return True
        if not text.startswith("."):
            return False
        lowered = text.casefold()
        return lowered in {".help", ".status", ".reboot", ".debug"} or lowered.startswith((".set", ".score"))

    def _clean_messages(self, messages: list[OneBotMessage]) -> list[CleanedOneBotTurn]:
        return [self._clean_message(message) for message in messages]

    def _clean_message(self, message: OneBotMessage) -> CleanedOneBotTurn:
        turn = CleanTurn(
            original_text=message.text,
            text=message.text.strip(),
            removed_lines=(),
            reason="onebot_segments",
            references_bot=message.references_bot,
        )
        identity = message.canonical_turn_id
        self._turn_ledger.observe(
            turn_id=identity,
            sender=message.sender_name,
            clean_text=turn.text,
            raw_text=message.text,
            fingerprint=message.fingerprint,
            references_bot=turn.references_bot,
            metadata={
                "transport": "onebot11",
                "message_id": message.message_id,
                "group_id": message.group_id,
                "user_id": message.user_id,
                "turn_cleaning": turn.to_metadata(),
            },
        )
        return CleanedOneBotTurn(raw=message, turn=turn, identity=identity)

    def _send_preflight(self) -> dict[str, Any]:
        model_preflight = getattr(getattr(self.agent, "model_client", None), "cloud_loop_preflight", None)
        if callable(model_preflight):
            result = model_preflight()
            if not result.get("ok", False):
                return {
                    "ok": False,
                    "reason": result.get("reason", "provider_blocked"),
                    "detail": result.get("detail", "Provider is not ready for the OneBot loop."),
                    "provider": result,
                }

        status = self.gateway.status()
        status_dict = status.to_dict()
        if status.ready:
            return {"ok": True, "reason": "send_allowed", "onebot": status_dict}

        return {
            "ok": False,
            "reason": "onebot_not_ready",
            "detail": status.detail,
            "onebot": status_dict,
        }

    def _record_context_message(
        self,
        message: OneBotMessage | CleanedOneBotTurn,
        *,
        agent_reason: str,
        agent_action: str = "context_only",
    ) -> None:
        cleaned = message if isinstance(message, CleanedOneBotTurn) else self._clean_message(message)
        if not cleaned.text:
            return
        if self.store is None:
            return
        if cleaned.fingerprint in self._context_fingerprints or cleaned.identity in self._context_turn_ids:
            self._context_fingerprints.add(cleaned.fingerprint)
            self._context_turn_ids.add(cleaned.identity)
            self._turn_ledger.add_alias(cleaned.identity, cleaned.fingerprint)
            return
        self._context_fingerprints.add(cleaned.fingerprint)
        self._context_turn_ids.add(cleaned.identity)
        self._last_non_bot_message_at = time.time()
        if agent_action == "context_only":
            self._turn_ledger.mark_context_only(
                cleaned.identity,
                metadata={"fingerprint": cleaned.fingerprint, "agent_reason": agent_reason},
            )
        self.store.append_event(
            source=cleaned.sender_name,
            kind="group_message",
            content=cleaned.text,
            metadata={
                "origin": "onebot_loop",
                "transport": "onebot11",
                "message_id": cleaned.raw.message_id,
                "source_message_ids": cleaned.source_message_ids,
                "self_id": cleaned.raw.self_id,
                "group_id": cleaned.raw.group_id,
                "user_id": cleaned.raw.user_id,
                "sender_name": cleaned.sender_name,
                "clean_text": cleaned.text,
                "agent_action": agent_action,
                "agent_reason": agent_reason,
                "fingerprint": cleaned.fingerprint,
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

    def _with_loop_command_feedback(self, result):
        if result.reason != "status_requested":
            return result

        loop_state = "on" if self.running else "off"
        processor_state = "on" if self._processor_task is not None and not self._processor_task.done() else "off"
        status_line = f"- loop: {loop_state} (processor {processor_state}, pending {len(self._pending_messages)})"
        metadata = {**result.metadata, "loop_runtime_status": self._loop_runtime_status()}
        return replace(result, reply=f"{result.reply}\n{status_line}", metadata=metadata)

    def _loop_runtime_status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "processor_running": self._processor_task is not None and not self._processor_task.done(),
            "pending_message_count": len(self._pending_messages),
            "aggregating_message_count": len(self._pending_turn_groups),
            "debug_mode": self._debug_mode(),
        }

    def _debug_mode(self) -> int:
        settings = getattr(self.agent, "settings", None)
        try:
            return int(getattr(settings, "debug_mode", 0))
        except (TypeError, ValueError):
            return 0

    def _debug_mode_allows_sender(self, sender_name: str) -> bool:
        if self._debug_mode() != 1:
            return True
        return self._same_sender(sender_name, self.config.target_sender_name)

    def _should_send_debug_no_reply_notice(self, message: CleanedOneBotTurn, result) -> bool:
        if self._debug_mode() != 1:
            return False
        if not self._same_sender(message.sender_name, self.config.target_sender_name):
            return False
        if result.action != "no_reply":
            return False
        if result.reason in {"ignored_by_command", "empty_message", "empty_or_punctuation_only"}:
            return False
        return bool(result.reason)

    def _debug_no_reply_notice(self, result) -> str:
        return f"不输出：{result.reason}"

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
        metadata = asdict(decision)
        metadata.update(self._decision_index_fields(decision.metadata))
        self.store.append_event(
            source="loop",
            kind="loop_decision",
            content=f"{decision.action}: {decision.reason}",
            metadata=metadata,
        )

    def _decision_index_fields(self, metadata: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "message_identity",
            "source_fingerprint",
            "provider_trace_id",
            "assistant_event_id",
            "latency_seconds",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "token_usage",
            "engagement_decision",
            "engagement_signals",
            "thinking_level",
            "requested_thinking_level",
            "web_used",
            "search_used",
            "local_time_used",
            "web_query",
            "agent_action",
            "agent_reason",
        )
        return {key: metadata[key] for key in keys if key in metadata}

    def _message_status(self, message: CleanedOneBotTurn) -> dict[str, Any]:
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
            "token_usage",
            "engagement_decision",
            "engagement_signals",
            "thinking_level",
            "max_thinking_level",
            "requested_thinking_level",
            "thinking_complexity_level",
            "gate_decision",
            "placeholder_sent",
            "placeholder_text",
            "placeholder_send_result",
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
            "command_resolution_notice",
            "command_resolution",
            "loop_runtime_status",
            "debug_no_reply_notice",
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
        identity = self._message_identity(sender_name, text)
        return self._turn_ledger.is_closed(identity, fingerprint)

    def _message_queued(self, message: OneBotMessage | CleanedOneBotTurn) -> bool:
        cleaned = message if isinstance(message, CleanedOneBotTurn) else self._clean_message(message)
        return not self._turn_ledger.can_enqueue(cleaned.identity, cleaned.fingerprint)

    def _same_sender(self, value: str, target: str) -> bool:
        normalized = value.strip()
        expected = target.strip()
        if not normalized or not expected:
            return False
        return normalized == expected or normalized in expected or expected in normalized

    def _remember_seen_message(self, sender_name: str, text: str, fingerprint: str) -> None:
        identity = self._message_identity(sender_name, text)
        self._turn_ledger.observe(
            turn_id=identity,
            sender=sender_name,
            clean_text=text,
            raw_text=text,
            fingerprint=fingerprint,
            references_bot=False,
        )
        self._turn_ledger.mark_completed(identity, metadata={"fingerprint": fingerprint})

    def _clear_pending_messages(self) -> None:
        self._pending_messages.clear()
        self._pending_turn_groups.clear()
        self._turn_ledger.clear_active()
        self._active_message = None

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
            seen_at = self._event_timestamp(event.created_at)
            if seen_at < cutoff:
                continue

            metadata = event.metadata or {}
            if event.kind == "assistant_reply":
                self.remember_sent_text(str(event.content or ""))
                continue

            if event.kind == "group_message":
                self._hydrate_context_event(event, metadata)
                continue

            if event.kind != "loop_decision":
                continue

            decision_metadata = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
            if bool(metadata.get("sent")):
                send_result = decision_metadata.get("send_result")
                sent_text = decision_metadata.get("cleaned_reply")
                if not sent_text and isinstance(send_result, dict):
                    sent_text = send_result.get("text")
                self.remember_sent_text(str(sent_text or ""))
            sender_name = str(metadata.get("sender_name", ""))
            message_text = str(metadata.get("message_text", ""))
            if not sender_name or not message_text:
                continue

            identity = (
                str(metadata.get("message_identity", ""))
                or str(decision_metadata.get("message_identity", ""))
                or self._message_identity(sender_name, message_text)
            )
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

    def _hydrate_context_event(self, event: Any, metadata: dict[str, Any]) -> None:
        sender_name = str(metadata.get("sender_name") or event.source)
        message_text = str(metadata.get("clean_text") or event.content)
        if not sender_name or not message_text:
            return

        identity = str(metadata.get("clean_identity") or self._message_identity(sender_name, message_text))
        fingerprint = str(metadata.get("fingerprint") or "")
        already_closed = self._turn_ledger.is_closed(identity, fingerprint)
        self._context_turn_ids.add(identity)
        if fingerprint:
            self._context_fingerprints.add(fingerprint)

        self._turn_ledger.observe(
            turn_id=identity,
            sender=sender_name,
            clean_text=message_text,
            raw_text=str(metadata.get("raw_message_text") or event.content),
            fingerprint=fingerprint,
            references_bot=bool((metadata.get("turn_cleaning") or {}).get("references_bot")),
            metadata={"source": "recent_group_message"},
        )
        if not already_closed:
            self._turn_ledger.mark_context_only(identity, metadata={"source": "recent_group_message"})

    def _event_timestamp(self, created_at: str) -> float:
        try:
            return datetime.fromisoformat(created_at).timestamp()
        except ValueError:
            return time.time()
