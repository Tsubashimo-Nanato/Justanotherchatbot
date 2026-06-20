from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from local_qq_agent.agent import LocalAgent, PersonaGuard, SocialStateTracker
from local_qq_agent.agent.context import ContextBuilder
from local_qq_agent.agent.style_learning import StyleAnchorDistiller, export_style_distillation_bundle
from local_qq_agent.config import AutonomyConfig, MemoryConfig, ModelConfig, PersonaConfig, QQConfig, WebConfig
from local_qq_agent.memory import SQLiteMemoryStore
from local_qq_agent.model import (
    download_model,
    model_profiles,
    restart_llama_server,
    run_offload_benchmark,
    set_active_model_profile,
    stop_port_listener,
)
from local_qq_agent.model.runtime import collect_model_runtime
from local_qq_agent.paths import ensure_parent, project_path
from local_qq_agent.provider import ProviderRuntime
from local_qq_agent.qq import QQWindowAdapter
from local_qq_agent.server.agent_loop import AgentLoop
from local_qq_agent.server.debug_timeline import build_debug_timeline
from local_qq_agent.server.debug_page import DEBUG_HTML
from local_qq_agent.server.instance_guard import AgentInstanceGuard
from local_qq_agent.server.reboot import AgentRebooter
from local_qq_agent.web import BrowserReader, SearxngClient, WebResearcher


class ChatSimulateRequest(BaseModel):
    user_name: str = Field(default="tester", max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    external_context: str = Field(default="", max_length=8000)


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=50)


class MemorySaveRequest(BaseModel):
    id: int | None = Field(default=None, ge=1)
    kind: str = Field(default="working_context", min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(default=0.7, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryDeleteRequest(BaseModel):
    id: int | None = Field(default=None, ge=1)
    query: str = Field(default="", max_length=500)
    limit: int = Field(default=50, ge=1, le=100)


class ShortTermEventSaveRequest(BaseModel):
    source: str = Field(default="debug_ui", min_length=1, max_length=120)
    kind: str = Field(default="manual_context", min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class BrowserReadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class QQSendRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AgentSettingsRequest(BaseModel):
    default_thinking_level: int | None = Field(default=None, ge=0, le=3)
    activity: float | None = Field(default=None, ge=0, le=1)


class SocialStateOverrideRequest(BaseModel):
    user_name: str = Field(default="", max_length=120)
    global_mood: str = Field(default="", max_length=80)
    mood_intensity: float | None = Field(default=None, ge=0, le=1)
    mood_minutes: int = Field(default=120, ge=1, le=1440)
    affinity: float | None = Field(default=None, ge=0, le=1)
    note: str = Field(default="", max_length=1000)


class SocialGlobalOverrideRequest(BaseModel):
    global_mood: str = Field(default="", max_length=80)
    mood_intensity: float | None = Field(default=None, ge=0, le=1)
    mood_minutes: int = Field(default=120, ge=1, le=1440)
    global_affinity: float | None = Field(default=None, ge=0, le=1)
    note: str = Field(default="", max_length=1000)


class SocialProfileOverrideRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=120)
    affinity: float | None = Field(default=None, ge=0, le=1)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    language_preference: str = Field(default="", max_length=80)
    tone_preference: str = Field(default="", max_length=200)
    relationship_notes: str = Field(default="", max_length=1000)
    note: str = Field(default="", max_length=1000)


class ModelSmokeRequest(BaseModel):
    message: str = Field(default="用一句中文介绍你现在的运行状态。", min_length=1, max_length=1000)


class ModelOffloadBenchmarkRequest(BaseModel):
    profiles: list[str] = Field(default_factory=list, max_length=8)
    restore_loop: bool = True


class SpontaneousTopicRequest(BaseModel):
    context: str = Field(default="", max_length=4000)


class ManualForceReplyRequest(BaseModel):
    sender_name: str = Field(min_length=1, max_length=120)
    message_text: str = Field(min_length=1, max_length=4000)
    event_id: int | None = Field(default=None, ge=1)
    extra_instruction: str = Field(default="", max_length=2000)
    send_to_qq: bool = True


class ModelSwitchRequest(BaseModel):
    profile: str = Field(min_length=1, max_length=120)
    restart_loop: bool = True


class ProviderSwitchRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    restart_loop: bool = True


class ProviderApiKeyRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=4000)


class ProviderTestRequest(BaseModel):
    message: str = Field(default="Return a short JSON health check.", min_length=1, max_length=1000)


class Runtime:
    def __init__(self) -> None:
        self.model_config = ModelConfig.load()
        self.persona_config = PersonaConfig.load()
        self.memory_config = MemoryConfig.load()
        self.qq_config = QQConfig.load()
        self.autonomy_config = AutonomyConfig.load()
        self.web_config = WebConfig.load()

        self.store = SQLiteMemoryStore(self.memory_config.database_path)
        self.instance_guard = AgentInstanceGuard()
        self.instance_status = self.instance_guard.claim()
        self.provider_runtime = ProviderRuntime(store=self.store)
        self.model_clients = self.provider_runtime.build_clients(self.model_config)
        self.model_client = self.model_clients.primary
        self._refresh_generated_style_anchor()
        self.persona_guard = PersonaGuard(self.persona_config)
        self.social_state = SocialStateTracker(self.store)
        self.context_builder = ContextBuilder(self.store, self.persona_guard, self.social_state)
        self.search = SearxngClient(self.web_config)
        self.browser = BrowserReader(self.web_config)
        self.researcher = WebResearcher(self.search, self.browser)
        self.agent = LocalAgent(
            store=self.store,
            persona_guard=self.persona_guard,
            context_builder=self.context_builder,
            model_client=self.model_client,
            gate_model_client=self.model_clients.gate,
            final_model_client=self.model_clients.final,
            utility_model_client=self.model_clients.utility,
            web_researcher=self.researcher,
            social_state=self.social_state,
            model_status_provider=self.model_status,
        )
        self.qq = QQWindowAdapter(self.qq_config)
        self.rebooter = AgentRebooter()
        self.loop = AgentLoop(
            agent=self.agent,
            qq=self.qq,
            store=self.store,
            config=self.qq_config,
            autonomy_config=self.autonomy_config,
            reboot_scheduler=lambda reason: self.rebooter.schedule(reason=reason),
            is_active_instance=self.instance_guard.is_current,
        )

    def rebuild_agent(self, *, refresh_style_anchor: bool = True) -> None:
        self.model_config = ModelConfig.load()
        self.persona_config = PersonaConfig.load()
        self.autonomy_config = AutonomyConfig.load()
        self.model_clients = self.provider_runtime.build_clients(self.model_config)
        self.model_client = self.model_clients.primary
        if refresh_style_anchor:
            self._refresh_generated_style_anchor()
        self.persona_guard = PersonaGuard(self.persona_config)
        self.context_builder = ContextBuilder(self.store, self.persona_guard, self.social_state)
        self.agent = LocalAgent(
            store=self.store,
            persona_guard=self.persona_guard,
            context_builder=self.context_builder,
            model_client=self.model_client,
            gate_model_client=self.model_clients.gate,
            final_model_client=self.model_clients.final,
            utility_model_client=self.model_clients.utility,
            web_researcher=self.researcher,
            social_state=self.social_state,
            model_status_provider=self.model_status,
        )
        self.loop = AgentLoop(
            agent=self.agent,
            qq=self.qq,
            store=self.store,
            config=self.qq_config,
            autonomy_config=self.autonomy_config,
            reboot_scheduler=lambda reason: self.rebooter.schedule(reason=reason),
            is_active_instance=self.instance_guard.is_current,
        )

    def refresh_generated_style_anchor(self) -> dict[str, Any] | None:
        return self._refresh_generated_style_anchor(force=True)

    def export_style_distillation_bundle(self) -> dict[str, Any] | None:
        config = self.persona_config
        if not config.style_learning_enabled:
            return None
        target = config.style_learning_target_user
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        output_path = project_path(f"personality/nanato/workspace/style_distillation_bundle_{timestamp}.json")
        instruction_path = project_path("personality/nanato/workspace/style_distillation_handoff.md")
        result = export_style_distillation_bundle(
            self.store,
            target_user=target,
            output_path=output_path,
            instruction_path=instruction_path,
            run_log_dir=config.style_learning_run_log_dir,
        )
        self.store.append_event(
            source="agent",
            kind="style_distillation_bundle_exported",
            content="Style distillation bundle exported for manual review.",
            metadata=result.to_dict(),
        )
        return result.to_dict()

    def _refresh_generated_style_anchor(self, *, force: bool = False) -> dict[str, Any] | None:
        config = self.persona_config
        if not config.style_learning_enabled:
            return None
        if not force and not config.style_learning_auto_distill:
            return None
        output_path = config.style_learning_generated_anchor_path
        if output_path is None:
            return None

        result = StyleAnchorDistiller(self.store).distill(
            target_user=config.style_learning_target_user,
            output_path=output_path,
            run_log_dir=config.style_learning_run_log_dir,
        )
        self.store.append_event(
            source="agent",
            kind="style_anchor_refresh",
            content="Generated style anchor refresh completed.",
            metadata=result.to_dict(),
        )
        return result.to_dict()

    def model_status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_runtime.status(),
            "active_profile": self.model_config.active_profile,
            "model": self.model_config.model,
            "target_path": str(self.model_config.download_target_path),
            "context_tokens_target": self.model_config.context_tokens_target,
            "server": {
                "n_ctx": self.model_config.server_n_ctx,
                "n_gpu_layers": self.model_config.server_n_gpu_layers,
                "n_batch": self.model_config.server_n_batch,
                "threads": self.model_config.server_n_threads,
                "threads_batch": self.model_config.server_n_threads_batch,
                "extra_args": list(self.model_config.server_extra_args),
            },
        }

    async def switch_model(self, profile: str, *, restart_loop: bool) -> dict[str, Any]:
        loop_was_running = self.loop.running
        if loop_was_running:
            await self.loop.stop()

        config = set_active_model_profile(profile)
        download_result = await asyncio.to_thread(download_model, config)
        restart_result = await asyncio.to_thread(restart_llama_server, config)
        if not restart_result.get("ready", {}).get("ok"):
            raise HTTPException(status_code=500, detail={"reason": "model_server_not_ready", "restart": restart_result})

        if self.provider_runtime.config.active_provider not in {"hybrid", "hybrid_responses"}:
            self.provider_runtime.switch_provider("local")
        self.rebuild_agent()
        loop_status: dict[str, Any] | None = None
        if loop_was_running and restart_loop:
            loop_status = await self.loop.start()

        self.store.append_event(
            source="server",
            kind="model_profile_switched",
            content=f"model profile switched to {self.model_config.active_profile}",
            metadata={
                "active_profile": self.model_config.active_profile,
                "model": self.model_config.model,
                "download": download_result,
                "restart": restart_result,
                "loop_was_running": loop_was_running,
                "loop_restarted": bool(loop_status and loop_status.get("running")),
                "persona": self.persona_guard.profile_status(),
            },
        )
        return {
            "active_profile": self.model_config.active_profile,
            "model": self.model_config.model,
            "download": download_result,
            "restart": restart_result,
            "loop_was_running": loop_was_running,
            "loop_status": loop_status or self.loop.status(),
            "memory": self.store.status(),
            "persona": self.persona_guard.profile_status(),
            "provider": self.provider_runtime.status(),
        }

    async def switch_provider(self, provider: str, *, restart_loop: bool) -> dict[str, Any]:
        loop_was_running = self.loop.running
        if loop_was_running and restart_loop:
            await self.loop.stop()

        provider_status = self.provider_runtime.switch_provider(provider)
        self.rebuild_agent()

        loop_status: dict[str, Any] | None = None
        if loop_was_running and restart_loop and self.provider_runtime.cloud_loop_allowed():
            loop_status = await self.loop.start()

        return {
            "provider": provider_status,
            "loop_was_running": loop_was_running,
            "loop_status": loop_status or self.loop.status(),
            "memory": self.store.status(),
            "persona": self.persona_guard.profile_status(),
        }


def latest_model_event(store: SQLiteMemoryStore) -> dict[str, Any] | None:
    for event in reversed(store.recent_events(limit=100)):
        used_model = bool(event.metadata.get("used_model"))
        if used_model or event.kind == "smoke_test":
            return asdict(event)
    return None


def create_app() -> FastAPI:
    runtime = Runtime()
    app = FastAPI(title="Local QQ Agent Demo", version="0.1.0")
    app.state.runtime = runtime

    @app.get("/debug", response_class=HTMLResponse)
    async def debug_page() -> str:
        return DEBUG_HTML

    @app.on_event("shutdown")
    async def shutdown_loop() -> None:
        await runtime.loop.stop()

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        model_status = await runtime.model_client.health()
        web_status = await runtime.search.health()
        return {
            "provider": runtime.provider_runtime.status(),
            "model": model_status,
            "model_profile": {
                "active_profile": runtime.model_config.active_profile,
                "model": runtime.model_config.model,
                "target_path": str(runtime.model_config.download_target_path),
                "server": {
                    "n_ctx": runtime.model_config.server_n_ctx,
                    "n_gpu_layers": runtime.model_config.server_n_gpu_layers,
                    "n_batch": runtime.model_config.server_n_batch,
                    "threads": runtime.model_config.server_n_threads,
                    "threads_batch": runtime.model_config.server_n_threads_batch,
                    "extra_args": list(runtime.model_config.server_extra_args),
                },
            },
            "memory": runtime.store.status(),
            "instance": runtime.instance_guard.status(),
            "qq": runtime.qq.status().to_dict(),
            "agent_loop": runtime.loop.status(),
            "agent_settings": runtime.agent.settings.to_dict(),
            "persona": runtime.persona_guard.profile_status(),
            "web": web_status,
        }

    @app.get("/api/debug/compact-status")
    async def compact_status() -> dict[str, Any]:
        loop_status = runtime.loop.status()
        qq_status = runtime.qq.status().to_dict()
        latest_decision = None
        recent_decisions = loop_status.get("recent_decisions") or []
        if recent_decisions:
            latest_decision = recent_decisions[-1]
        return {
            "provider": runtime.provider_runtime.status(),
            "model_profile": {
                "active_profile": runtime.model_config.active_profile,
                "model": runtime.model_config.model,
            },
            "qq": {
                "available": qq_status.get("available"),
                "armed": qq_status.get("armed"),
                "dry_run": qq_status.get("dry_run"),
                "active_group_name": qq_status.get("active_group_name"),
                "expected_group_name": qq_status.get("expected_group_name"),
                "group_matched": qq_status.get("group_matched"),
            },
            "agent_loop": {
                "running": loop_status.get("running"),
                "pending_message_count": loop_status.get("pending_message_count"),
                "aggregating_message_count": loop_status.get("aggregating_message_count"),
                "queued_message_count": loop_status.get("queued_message_count"),
                "inflight_message_count": loop_status.get("inflight_message_count"),
                "active_message": loop_status.get("active_message"),
                "activity": loop_status.get("activity"),
                "ledger": loop_status.get("ledger"),
                "latest_decision": latest_decision,
            },
            "instance": runtime.instance_guard.status(),
            "agent_settings": runtime.agent.settings.to_dict(),
        }

    @app.get("/api/debug/timeline")
    async def debug_timeline(limit: int = 80) -> dict[str, Any]:
        safe_limit = min(max(limit, 1), 200)
        source_events = runtime.store.recent_events(limit=max(safe_limit * 8, safe_limit), newest_first=False)
        return {
            "items": build_debug_timeline(source_events, limit=safe_limit),
            "source_event_count": len(source_events),
            "limit": safe_limit,
        }

    @app.get("/api/model/runtime")
    async def model_runtime() -> dict[str, Any]:
        return {
            "health": await runtime.model_client.health(),
            "provider": runtime.provider_runtime.status(),
            "profiles": model_profiles(),
            **collect_model_runtime(runtime.model_config),
            "latest_model_event": latest_model_event(runtime.store),
        }

    @app.get("/api/model/profiles")
    async def model_profile_list() -> dict[str, Any]:
        return model_profiles()

    @app.post("/api/model/switch")
    async def model_switch(request: ModelSwitchRequest) -> dict[str, Any]:
        return await runtime.switch_model(request.profile, restart_loop=request.restart_loop)

    @app.post("/api/model/stop-local")
    async def model_stop_local() -> dict[str, Any]:
        loop_was_running = runtime.loop.running
        if loop_was_running:
            await runtime.loop.stop()
        result = await asyncio.to_thread(stop_port_listener, runtime.model_config.server_port)
        runtime.provider_runtime.switch_provider("unloaded")
        runtime.rebuild_agent()
        runtime.store.append_event(
            source="model",
            kind="local_model_stopped",
            content=f"Stopped local model listener on port {runtime.model_config.server_port}",
            metadata={"stop_result": result, "loop_was_running": loop_was_running},
        )
        return {
            "stop_result": result,
            "provider": runtime.provider_runtime.status(),
            "loop_was_running": loop_was_running,
            "loop_status": runtime.loop.status(),
        }

    @app.get("/api/provider/status")
    async def provider_status() -> dict[str, Any]:
        return runtime.provider_runtime.status()

    @app.post("/api/provider/switch")
    async def provider_switch(request: ProviderSwitchRequest) -> dict[str, Any]:
        try:
            return await runtime.switch_provider(request.provider, restart_loop=request.restart_loop)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/provider/api-key")
    async def provider_api_key(request: ProviderApiKeyRequest) -> dict[str, Any]:
        try:
            status = runtime.provider_runtime.save_api_key(request.api_key)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        runtime.rebuild_agent()
        return status

    @app.post("/api/provider/test")
    async def provider_test(request: ProviderTestRequest) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": "You are running a provider connectivity test. Reply briefly."},
            {"role": "user", "content": request.message},
        ]
        reply = await runtime.model_client.chat(messages, max_tokens=128, operation="simple_chat")
        return {
            "content": reply.content,
            "model": reply.model,
            "latency_seconds": round(reply.latency_seconds, 3),
            "usage": reply.usage,
            "tokens_per_second": reply.tokens_per_second,
            "metadata": reply.metadata,
            "provider": runtime.provider_runtime.status(),
        }

    @app.post("/api/provider/duplicate-soak")
    async def provider_duplicate_soak() -> dict[str, Any]:
        result = runtime.provider_runtime.run_duplicate_soak()
        runtime.rebuild_agent()
        return result

    @app.get("/api/provider/traces")
    async def provider_traces(limit: int = 20) -> list[dict[str, Any]]:
        return runtime.provider_runtime.traces.recent(limit=min(max(limit, 1), 100))

    @app.get("/api/provider/traces/{trace_id}")
    async def provider_trace(trace_id: str) -> dict[str, Any]:
        trace = runtime.provider_runtime.traces.get(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return trace

    @app.get("/api/qq/status")
    async def qq_status() -> dict[str, Any]:
        return runtime.qq.status().to_dict()

    @app.get("/api/agent-loop/status")
    async def agent_loop_status() -> dict[str, Any]:
        return runtime.loop.status()

    @app.get("/api/agent/settings")
    async def agent_settings() -> dict[str, Any]:
        return runtime.agent.settings.to_dict()

    @app.post("/api/agent/settings")
    async def agent_settings_update(request: AgentSettingsRequest) -> dict[str, Any]:
        return runtime.agent.update_settings(
            default_thinking_level=request.default_thinking_level,
            activity=request.activity,
            source="debug_ui",
        )

    @app.post("/api/agent/reboot")
    async def agent_reboot() -> dict[str, Any]:
        runtime.store.append_event(
            source="server",
            kind="reboot_scheduled",
            content="Agent service reboot scheduled from API",
            metadata={"scope": "agent_only", "persona_reload_policy": "restart_required"},
        )
        return runtime.rebooter.schedule(reason="api")

    @app.post("/api/system/restart")
    async def system_restart() -> dict[str, Any]:
        runtime.store.append_event(
            source="server",
            kind="reboot_scheduled",
            content="Full service restart scheduled from API",
            metadata={"scope": "full_service", "frontend_expected_to_reconnect": True},
        )
        return runtime.rebooter.schedule(reason="full_restart_api")

    @app.post("/api/persona/style-anchor/refresh")
    async def persona_style_anchor_refresh() -> dict[str, Any]:
        result = runtime.refresh_generated_style_anchor()
        runtime.rebuild_agent(refresh_style_anchor=False)
        return {
            "style_anchor_refresh": result,
            "persona": runtime.persona_guard.profile_status(),
        }

    @app.post("/api/persona/style-distillation/export")
    async def persona_style_distillation_export() -> dict[str, Any]:
        result = runtime.export_style_distillation_bundle()
        return {
            "style_distillation_bundle": result,
            "instruction_path": str(project_path("personality/nanato/workspace/style_distillation_handoff.md")),
        }

    @app.post("/api/agent-loop/start")
    async def agent_loop_start() -> dict[str, Any]:
        return await runtime.loop.start()

    @app.post("/api/agent-loop/stop")
    async def agent_loop_stop() -> dict[str, Any]:
        return await runtime.loop.stop()

    @app.post("/api/agent-loop/tick")
    async def agent_loop_tick() -> dict[str, Any]:
        return await runtime.loop.tick()

    @app.post("/api/agent-loop/collect-scrollback")
    async def agent_loop_collect_scrollback(pages: int = 3) -> dict[str, Any]:
        return await runtime.loop.collect_scrollback(pages=pages)

    @app.post("/api/agent-loop/manual-reply")
    async def agent_loop_manual_reply(request: ManualForceReplyRequest) -> dict[str, Any]:
        try:
            return await runtime.loop.force_reply(
                sender_name=request.sender_name,
                message_text=request.message_text,
                event_id=request.event_id,
                extra_instruction=request.extra_instruction,
                send_to_qq=request.send_to_qq,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/events/recent")
    async def recent_events(limit: int = 30) -> list[dict[str, Any]]:
        safe_limit = min(max(limit, 1), 100)
        return [asdict(event) for event in runtime.store.recent_events(limit=safe_limit, newest_first=True)]

    @app.post("/api/events/save")
    async def event_save(request: ShortTermEventSaveRequest) -> dict[str, Any]:
        event = runtime.store.append_event(
            source=request.source,
            kind=request.kind,
            content=request.content,
            metadata={**request.metadata, "source": "debug_ui_manual_short_term"},
        )
        return asdict(event)

    @app.get("/api/events/stream")
    async def event_stream() -> StreamingResponse:
        async def stream_events():
            events = [asdict(event) for event in runtime.store.recent_events(limit=30)]
            yield f"data: {json.dumps(events, ensure_ascii=False)}\n\n"

        return StreamingResponse(stream_events(), media_type="text/event-stream")

    @app.post("/api/chat/simulate")
    async def simulate_chat(request: ChatSimulateRequest) -> dict[str, Any]:
        result = await runtime.agent.simulate(
            user_name=request.user_name,
            message=request.message,
            external_context=request.external_context,
        )
        return result.to_dict()

    @app.post("/api/model/smoke")
    async def model_smoke(request: ModelSmokeRequest) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": "你正在进行本地模型烟测。回答要短。"},
            {"role": "user", "content": request.message},
        ]
        reply = await runtime.model_client.chat(messages)
        runtime.store.append_event(
            source="model",
            kind="smoke_test",
            content=reply.content,
            metadata={
                "latency_seconds": round(reply.latency_seconds, 3),
                "usage": reply.usage,
                "tokens_per_second": reply.tokens_per_second,
            },
        )
        return {
            "content": reply.content,
            "model": reply.model,
            "latency_seconds": round(reply.latency_seconds, 3),
            "usage": reply.usage,
            "tokens_per_second": reply.tokens_per_second,
        }

    @app.post("/api/model/benchmark-offload")
    async def model_benchmark_offload(request: ModelOffloadBenchmarkRequest) -> dict[str, Any]:
        loop_was_running = runtime.loop.running
        if loop_was_running:
            await runtime.loop.stop()

        runtime.store.append_event(
            source="model",
            kind="offload_benchmark_started",
            content="Model offload benchmark started",
            metadata={"profiles": request.profiles, "loop_was_running": loop_was_running},
        )
        result = await run_offload_benchmark(
            profile_names=request.profiles or None,
            restore_profile=runtime.model_config.active_profile,
        )
        if loop_was_running and request.restore_loop:
            result["loop_restore"] = await runtime.loop.start()
        else:
            result["loop_restore"] = {"restored": False, "loop_was_running": loop_was_running}

        runtime.store.append_event(
            source="model",
            kind="offload_benchmark_finished",
            content=str(result.get("artifact_path", "")),
            metadata={
                "artifact_path": result.get("artifact_path"),
                "profiles": [item.get("profile") for item in result.get("results", [])],
                "loop_restore": result.get("loop_restore"),
            },
        )
        return result

    @app.post("/api/memory/search")
    async def memory_search(request: MemorySearchRequest) -> list[dict[str, Any]]:
        return [asdict(memory) for memory in runtime.store.search_memories(request.query, request.limit)]

    @app.get("/api/memory/recent")
    async def memory_recent(limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = min(max(limit, 1), 100)
        return [asdict(memory) for memory in runtime.store.recent_memories(limit=safe_limit, newest_first=True)]

    @app.post("/api/memory/save")
    async def memory_save(request: MemorySaveRequest) -> dict[str, Any]:
        metadata = {**request.metadata, "source": "debug_ui_manual_long_term"}
        if request.id is None:
            memory = runtime.store.add_memory(
                kind=request.kind,
                summary=request.summary,
                confidence=request.confidence,
                metadata=metadata,
            )
        else:
            try:
                memory = runtime.store.update_memory(
                    memory_id=request.id,
                    kind=request.kind,
                    summary=request.summary,
                    confidence=request.confidence,
                    metadata=metadata,
                )
            except KeyError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error

        runtime.store.append_event(
            source="memory",
            kind="memory_manual_save",
            content=f"{memory.kind}: {memory.summary}",
            metadata={"memory_id": memory.id, "operation": "update" if request.id else "create"},
        )
        return asdict(memory)

    @app.post("/api/memory/delete")
    async def memory_delete(request: MemoryDeleteRequest) -> dict[str, Any]:
        if request.id is not None:
            deleted = runtime.store.delete_memory_by_id(request.id)
            deleted_items = [] if deleted is None else [deleted]
        elif request.query.strip():
            deleted_items = runtime.store.delete_memories_matching(request.query, limit=request.limit)
        else:
            raise HTTPException(status_code=400, detail="memory delete requires id or query")

        runtime.store.append_event(
            source="memory",
            kind="memory_manual_delete",
            content=f"Deleted {len(deleted_items)} memory rows",
            metadata={
                "id": request.id,
                "query": request.query,
                "deleted_count": len(deleted_items),
                "deleted_memory_ids": [memory.id for memory in deleted_items],
            },
        )
        return {
            "deleted_count": len(deleted_items),
            "deleted": [asdict(memory) for memory in deleted_items],
        }

    @app.get("/api/social-state")
    async def social_state(user_name: str = "group member") -> dict[str, Any]:
        return runtime.social_state.snapshot(user_name).to_dict()

    @app.get("/api/social-state/users")
    async def social_state_users() -> dict[str, Any]:
        return {"users": runtime.social_state.user_profiles()}

    @app.get("/api/social-state/profile")
    async def social_state_profile(user_name: str) -> dict[str, Any]:
        profile = runtime.social_state.user_profile(user_name).to_dict()
        return {
            "profile": profile,
            "snapshot": runtime.social_state.snapshot(user_name).to_dict(),
        }

    @app.post("/api/social-state/profile/override")
    async def social_state_profile_override(request: SocialProfileOverrideRequest) -> dict[str, Any]:
        profile = runtime.social_state.override_profile(
            user_name=request.user_name,
            affinity=request.affinity,
            aliases=tuple(alias.strip() for alias in request.aliases if alias.strip()),
            language_preference=request.language_preference,
            tone_preference=request.tone_preference,
            relationship_notes=request.relationship_notes,
            note=request.note,
        )
        return {
            "profile": profile.to_dict(),
            "snapshot": runtime.social_state.snapshot(request.user_name).to_dict(),
        }

    @app.get("/api/social-state/global")
    async def social_state_global() -> dict[str, Any]:
        return runtime.social_state.global_state()

    @app.post("/api/social-state/global")
    async def social_state_global_override(request: SocialGlobalOverrideRequest) -> dict[str, Any]:
        return runtime.social_state.override_global(
            global_mood=request.global_mood,
            mood_intensity=request.mood_intensity,
            mood_minutes=request.mood_minutes,
            global_affinity=request.global_affinity,
            note=request.note,
        )

    @app.get("/api/social-state/changes")
    async def social_state_changes(limit: int = 30) -> dict[str, Any]:
        safe_limit = max(1, min(limit, 100))
        return {"changes": runtime.social_state.recent_changes(limit=safe_limit)}

    @app.post("/api/social-state/override")
    async def social_state_override(request: SocialStateOverrideRequest) -> dict[str, Any]:
        return runtime.social_state.override(
            user_name=request.user_name,
            global_mood=request.global_mood,
            mood_intensity=request.mood_intensity,
            mood_minutes=request.mood_minutes,
            affinity=request.affinity,
            note=request.note,
        ).to_dict()

    @app.post("/api/agent/spontaneous")
    async def agent_spontaneous(request: SpontaneousTopicRequest) -> dict[str, Any]:
        message = (
            "详细分析最近群聊上下文和当前角色状态，自发产生一个适合发到群里的短话题。"
            "不要解释调试状态，不要说自己在生成话题，只输出会发出去的内容。"
        )
        if request.context.strip():
            message = f"{message}\n补充上下文：{request.context.strip()}"
        result = await runtime.agent.respond_to_incoming(
            user_name="debug_ui_spontaneous",
            message=f"{message} .enforce .think 3",
        )
        payload = result.to_dict()
        payload["spontaneous"] = {"manual": True, "thinking_level_requested": 3, "sent_to_qq": False}
        return payload

    @app.post("/api/web/search")
    async def web_search(request: WebSearchRequest) -> list[dict[str, str]]:
        try:
            results = await runtime.search.search(request.query, request.limit)
        except Exception as error:
            runtime.store.append_event(
                source="web",
                kind="search_error",
                content=request.query,
                metadata={"error": str(error)},
            )
            raise HTTPException(status_code=502, detail=str(error)) from error

        runtime.store.append_event(
            source="web",
            kind="search",
            content=request.query,
            metadata={"result_count": len(results)},
        )
        return [result.to_dict() for result in results]

    @app.post("/api/web/read")
    async def web_read(request: BrowserReadRequest) -> dict[str, Any]:
        result = await runtime.browser.read(request.url)
        runtime.store.append_event(
            source="web",
            kind="browser_read",
            content=request.url,
            metadata={"ok": result.ok, "reason": result.reason},
        )
        return result.to_dict()

    @app.post("/api/qq/arm")
    async def qq_arm() -> dict[str, Any]:
        status = runtime.qq.arm().to_dict()
        send_result = (await asyncio.to_thread(runtime.qq.send_text, "QQ armed")).to_dict()
        focus_result = await asyncio.to_thread(runtime.qq.focus_window, maximize=True)
        payload = {
            **status,
            "arm_notice": send_result,
            "focus": focus_result,
        }
        runtime.store.append_event(
            source="qq",
            kind="armed",
            content="QQ armed",
            metadata=payload,
        )
        return payload

    @app.post("/api/qq/disarm")
    async def qq_disarm() -> dict[str, Any]:
        return runtime.qq.disarm().to_dict()

    @app.post("/api/qq/probe")
    async def qq_probe() -> dict[str, Any]:
        try:
            result = runtime.qq.probe()
        except Exception as error:
            runtime.store.append_event(
                source="qq",
                kind="probe_error",
                content="QQ window probe failed",
                metadata={"error": str(error)},
            )
            raise HTTPException(status_code=502, detail=str(error)) from error

        artifact_path = project_path("artifacts/qq_uia_probe.json")
        ensure_parent(artifact_path)
        artifact_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        runtime.store.append_event(
            source="qq",
            kind="probe",
            content="QQ window probed",
            metadata={"artifact_path": str(artifact_path), "control_count": result.get("control_count")},
        )
        return result

    @app.get("/api/qq/read")
    async def qq_read() -> dict[str, Any]:
        try:
            result = runtime.qq.read_visible_context()
        except Exception as error:
            runtime.store.append_event(
                source="qq",
                kind="read_error",
                content="QQ visible context read failed",
                metadata={"error": str(error)},
            )
            raise HTTPException(status_code=502, detail=str(error)) from error
        payload = result.to_dict()
        payload["context_recording"] = runtime.loop.record_visible_read(result)
        return payload

    @app.get("/api/qq/read/scrollback")
    async def qq_read_scrollback(pages: int = 3) -> dict[str, Any]:
        try:
            result = runtime.qq.read_scrollback_context(pages=pages)
        except Exception as error:
            runtime.store.append_event(
                source="qq",
                kind="scrollback_read_error",
                content="QQ scrollback context read failed",
                metadata={"error": str(error), "pages": pages},
            )
            raise HTTPException(status_code=502, detail=str(error)) from error
        payload = result.to_dict()
        payload["context_recording"] = runtime.loop.record_visible_read(result)
        return payload

    @app.post("/api/qq/send")
    async def qq_send(request: QQSendRequest) -> dict[str, Any]:
        result = runtime.qq.send_text(request.text)
        runtime.store.append_event(
            source="qq",
            kind="send_attempt",
            content=request.text,
            metadata=result.to_dict(),
        )
        return result.to_dict()

    return app
