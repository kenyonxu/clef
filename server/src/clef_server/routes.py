"""FastAPI routes — REST endpoints + SSE streaming."""

import asyncio
import importlib
import json
import logging
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from clef_server.sessions import SessionManager
from clef_server.orchestrator import get_session_manager

logger = logging.getLogger(__name__)

router = APIRouter()
_session_manager = get_session_manager()


def create_router() -> APIRouter:
    return router


# === Request/Response Models ===

class ComposeRequest(BaseModel):
    prompt: str = Field(..., description="Music composition description", min_length=1)
    plan: dict | None = Field(None, description="Optional pre-defined plan.json")


class ComposeResponse(BaseModel):
    session_id: str
    status: str


class StatusResponse(BaseModel):
    session_id: str
    status: str
    user_prompt: str = ""
    workflow_steps: list[dict] = []
    output_files: list[str] = []
    error: str | None = None
    current_phase: str = ""
    confirmation_data: dict | None = None
    sample_round: int = 0
    iteration_count: int = 0


class CancelResponse(BaseModel):
    session_id: str
    status: str


class SessionsResponse(BaseModel):
    sessions: list[dict]


class ConfirmRequest(BaseModel):
    action: Literal["continue", "cancel", "revise"] = Field(..., description="'continue', 'revise', or 'cancel'")
    feedback: str | None = Field(None, description="Optional user feedback text", max_length=2000)


class PermissionUpdateRequest(BaseModel):
    denied_tools: list[str] = Field(default_factory=list, description="Tools to deny")
    allowed_overrides: list[str] = Field(default_factory=list, description="Tools to re-enable (intersected with base map)")

    model_config = {"extra": "forbid"}


# === Settings Models ===

class SettingsResponse(BaseModel):
    output_dir: str = ""
    sf2_path: str = ""
    sf2_name: str = ""
    sf2_preset_count: int = 0
    max_iterations: int = 3
    review_threshold: int = 7
    skip_review: bool = False


class SettingsUpdateRequest(BaseModel):
    output_dir: str | None = Field(None, max_length=260)
    sf2_path: str | None = Field(None, max_length=260)
    max_iterations: int | None = Field(None, ge=1, le=20)
    review_threshold: int | None = Field(None, ge=1, le=10)
    skip_review: bool | None = None


class ProviderInfo(BaseModel):
    alias: str
    model_id: str = ""
    base_url: str = ""
    api_key_masked: str = ""
    is_configured: bool = False


class ProviderListResponse(BaseModel):
    anthropic: ProviderInfo | None = None
    openai_compat: list[ProviderInfo] = []


class OpenAICompatEntry(BaseModel):
    model_id: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)


class ProviderUpdateRequest(BaseModel):
    anthropic_api_key: str | None = Field(None, min_length=1)
    anthropic_model: str | None = Field(None, min_length=1)
    openai_compat: dict[str, OpenAICompatEntry] | None = None
    remove_openai_compat: list[str] | None = None


class AgentInfo(BaseModel):
    name: str
    model_alias: str
    temperature: float
    skills: list[str] = []
    tools: list[str] = []


class AgentListResponse(BaseModel):
    agents: list[AgentInfo] = []


class AgentUpdateRequest(BaseModel):
    agents: dict[str, dict] | None = None


# === Workflow Execution ===

async def _run_workflow(session_id: str, prompt: str, plan: dict | None, workdir: str) -> None:
    """Start the compose workflow via orchestrator."""
    session = _session_manager.get(session_id)
    if not session:
        logger.error(f"Session {session_id} not found")
        return

    try:
        from clef_server.config import load_provider_config, load_settings
        from clef_server.providers import create_providers
        from clef_server.orchestrator import ComposeOrchestrator

        server_root = Path(__file__).resolve().parent.parent.parent
        provider_config = load_provider_config(server_root / "config" / "providers.yaml")
        providers = create_providers(provider_config)
        settings = load_settings(server_root)

        orchestrator = ComposeOrchestrator(session_id=session_id, providers=providers, workdir=workdir, settings=settings)
        await orchestrator.start(prompt)

    except Exception as e:
        logger.exception(f"Session {session_id}: workflow failed")
        session.set_failed(error=str(e))


# === Endpoints ===

@router.post("/compose", response_model=ComposeResponse)
async def create_compose(req: ComposeRequest):
    session_id = f"clef-{uuid.uuid4().hex[:8]}"
    from clef_server.config import load_settings, generate_workdir
    settings = load_settings(_get_server_root())
    workdir = generate_workdir(settings, session_id, req.prompt)
    Path(workdir).mkdir(parents=True, exist_ok=True)
    session = _session_manager.create(
        user_prompt=req.prompt,
        workdir=workdir,
        plan=req.plan,
        session_id=session_id,
    )
    task = asyncio.create_task(_run_workflow(session_id, req.prompt, req.plan, workdir))
    task.add_done_callback(lambda t: t.exception() and logger.error(f"Workflow task failed: {t.exception()}"))
    return ComposeResponse(session_id=session.session_id, status=session.status)


def _enrich_steps_with_models(steps: list[dict]) -> list[dict]:
    """Inject model_alias into each step's agents list from agents.yaml."""
    try:
        from clef_server.config import load_agent_configs
        configs = load_agent_configs(_get_server_root() / "config" / "agents.yaml")
    except Exception:
        logger.warning("Failed to enrich steps with model info", exc_info=True)
        return steps
    agent_models = {name: cfg.model_alias for name, cfg in configs.items()}
    enriched = []
    for step in steps:
        s = dict(step)
        if s.get("agents"):
            s["agents"] = [
                {"name": a, "model": agent_models.get(a, "?")}
                for a in s["agents"]
            ]
        enriched.append(s)
    return enriched


@router.get("/status/{session_id}", response_model=StatusResponse)
async def get_status(session_id: str):
    session = _session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return StatusResponse(
        session_id=session.session_id,
        status=session.status,
        user_prompt=session.user_prompt,
        workflow_steps=_enrich_steps_with_models(session.get_workflow_steps()),
        output_files=session.output_files,
        error=session.error,
        current_phase=session.current_phase,
        confirmation_data=session.confirmation_data,
        sample_round=session.sample_round,
        iteration_count=session.iteration_count,
    )


@router.get("/status/{session_id}/stream")
async def status_stream(session_id: str):
    session = _session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        from sse_starlette.sse import EventSourceResponse
    except ImportError:
        raise HTTPException(status_code=503, detail="SSE not available (sse-starlette not installed)")

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        session.add_event_listener(queue)
        try:
            # Send initial state dump so client can catch up
            initial = {
                "type": "state",
                "session_id": session_id,
                "current_phase": session.current_phase,
                "sub_steps": session.sub_steps,
                "workflow_steps": session.get_workflow_steps(),
            }
            yield {"event": "state", "data": json.dumps(initial, ensure_ascii=False)}

            # Stream events until session reaches terminal state
            terminal = {"done", "failed", "cancelled"}
            while session.status not in terminal:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": event["event"], "data": event["data"]}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": json.dumps({"t": time.time()})}
        finally:
            session.remove_event_listener(queue)

    return EventSourceResponse(event_generator())


@router.get("/result/{session_id}")
async def get_result(session_id: str):
    session = _session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "done":
        raise HTTPException(status_code=400, detail=f"Session status is '{session.status}', not 'done'")
    return {
        "session_id": session.session_id,
        "output_files": session.output_files,
        "workdir": session.workdir,
    }


@router.post("/confirm/{session_id}")
async def confirm_session(session_id: str, req: ConfirmRequest):
    session = _session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "awaiting_confirm":
        raise HTTPException(status_code=400, detail=f"Session is '{session.status}', not awaiting confirmation")

    if req.action == "cancel":
        session.set_cancelled()
        return {"session_id": session.session_id, "status": session.status}

    # Snapshot confirmation data before clearing
    saved_confirmation_data = session.confirmation_data
    saved_current_phase = session.current_phase
    feedback = req.feedback
    action = req.action
    workdir = session.workdir

    # Clear state immediately — prevents stale UI after background task starts
    session.confirmation_data = None
    session.set_running()

    async def _resume_workflow() -> None:
        try:
            from clef_server.config import load_provider_config, load_settings
            from clef_server.providers import create_providers
            from clef_server.orchestrator import ComposeOrchestrator

            server_root = Path(__file__).resolve().parent.parent.parent
            provider_config = load_provider_config(server_root / "config" / "providers.yaml")
            providers = create_providers(provider_config)
            settings = load_settings(server_root)

            orchestrator = ComposeOrchestrator(session_id=session_id, providers=providers, workdir=workdir, settings=settings)
            await orchestrator.resume(user_feedback=feedback, action=action, saved_confirmation_data=saved_confirmation_data)
        except Exception as e:
            logger.exception(f"Session {session_id}: resume failed")
            sess = _session_manager.get(session_id)
            if sess:
                sess.set_failed(error=str(e))

    task = asyncio.create_task(_resume_workflow())
    task.add_done_callback(lambda t: t.exception() and logger.error(f"Resume task failed: {t.exception()}"))

    return {"session_id": session.session_id, "status": session.status, "current_phase": saved_current_phase}


@router.post("/cancel/{session_id}", response_model=CancelResponse)
async def cancel_session(session_id: str):
    session = _session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        session.set_cancelled()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CancelResponse(session_id=session.session_id, status=session.status)


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions():
    sessions = _session_manager.list_sessions()
    return SessionsResponse(sessions=[s.to_dict() for s in sessions])


@router.patch("/sessions/{session_id}/permissions")
async def update_permissions(session_id: str, req: PermissionUpdateRequest):
    session = _session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    from clef_server.sessions import ToolPermissions
    session.tool_permissions = ToolPermissions(
        denied_tools=frozenset(req.denied_tools),
        allowed_overrides=frozenset(req.allowed_overrides),
    )
    return {
        "denied_tools": sorted(session.tool_permissions.denied_tools),
        "allowed_overrides": sorted(session.tool_permissions.allowed_overrides),
    }


@router.get("/sessions/{session_id}/permissions")
async def get_permissions(session_id: str):
    session = _session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "denied_tools": sorted(session.tool_permissions.denied_tools),
        "allowed_overrides": sorted(session.tool_permissions.allowed_overrides),
    }


@router.get("/tools")
async def list_tools():
    from clef_server.tools import TOOLS_REGISTRY, _TOOL_META
    result = []
    for name in TOOLS_REGISTRY:
        meta = _TOOL_META.get(name)
        result.append({
            "name": name,
            "safety": meta.safety.value if meta else "unknown",
        })
    return result


# === Settings Endpoints ===

_server_start_time = time.time()


def _get_server_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _get_sf2_meta(sf2_path: str) -> dict:
    """Read SF2 profile metadata (name, preset_count) for settings response."""
    if not sf2_path:
        return {"sf2_name": "", "sf2_preset_count": 0}
    from clef_server.sf2_profile import load_sf2_profile
    profile = load_sf2_profile(sf2_path)
    if not profile:
        return {"sf2_name": "", "sf2_preset_count": 0}
    return {
        "sf2_name": profile.get("sf2_name", ""),
        "sf2_preset_count": profile.get("preset_count", 0),
    }


def _mask_api_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***" if key else ""
    return key[:3] + "****" + key[-4:]


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    from clef_server.config import load_settings
    settings = load_settings(_get_server_root())
    # Enrich with SF2 profile metadata (blocking I/O → thread)
    sf2_meta = await asyncio.to_thread(_get_sf2_meta, settings.get("sf2_path", ""))
    settings.update(sf2_meta)
    return SettingsResponse(**settings)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(req: SettingsUpdateRequest):
    from clef_server.config import load_settings, save_settings
    settings = load_settings(_get_server_root())
    update_data = req.model_dump(exclude_none=True)
    # Validate sf2_path: must exist, be a file, and have .sf2 extension
    if "sf2_path" in update_data and update_data["sf2_path"]:
        sf2 = Path(update_data["sf2_path"])
        if not sf2.exists() or not sf2.is_file():
            raise HTTPException(status_code=400, detail=f"SF2 file not found: {update_data['sf2_path']}")
        if sf2.suffix.lower() != ".sf2":
            raise HTTPException(status_code=400, detail="SF2 path must have .sf2 extension")
    settings.update(update_data)
    save_settings(_get_server_root(), settings)
    # Enrich with SF2 profile metadata (blocking I/O → thread)
    sf2_meta = await asyncio.to_thread(_get_sf2_meta, settings.get("sf2_path", ""))
    settings.update(sf2_meta)
    return SettingsResponse(**settings)


@router.get("/settings/providers", response_model=ProviderListResponse)
async def get_providers():
    from clef_server.config import load_provider_config
    path = _get_server_root() / "config" / "providers.yaml"
    config = load_provider_config(path)

    anthropic = None
    if config.anthropic:
        anthropic = ProviderInfo(
            alias="anthropic",
            model_id=config.anthropic.default_model,
            api_key_masked=_mask_api_key(config.anthropic.api_key),
            is_configured=bool(config.anthropic.api_key),
        )

    openai_compat = []
    for alias, cfg in config.openai_compat.items():
        openai_compat.append(ProviderInfo(
            alias=alias,
            model_id=cfg.model_id,
            base_url=cfg.base_url,
            api_key_masked=_mask_api_key(cfg.api_key),
            is_configured=bool(cfg.api_key),
        ))

    return ProviderListResponse(anthropic=anthropic, openai_compat=openai_compat)


@router.put("/settings/providers", response_model=ProviderListResponse)
async def update_providers(req: ProviderUpdateRequest):
    from clef_server.config import load_provider_config_raw, save_provider_config
    path = _get_server_root() / "config" / "providers.yaml"
    raw = load_provider_config_raw(path)

    if req.anthropic_api_key is not None or req.anthropic_model is not None:
        if "anthropic" not in raw:
            raw["anthropic"] = {}
        if req.anthropic_api_key is not None:
            raw["anthropic"]["api_key"] = req.anthropic_api_key
        if req.anthropic_model is not None:
            raw["anthropic"]["default_model"] = req.anthropic_model

    if req.remove_openai_compat:
        oc = raw.get("openai_compat", {})
        for alias in req.remove_openai_compat:
            oc.pop(alias, None)

    if req.openai_compat:
        if "openai_compat" not in raw:
            raw["openai_compat"] = {}
        for alias, cfg in req.openai_compat.items():
            raw["openai_compat"][alias] = cfg.model_dump() if hasattr(cfg, "model_dump") else cfg

    save_provider_config(path, raw)
    return await get_providers()


@router.get("/settings/agents", response_model=AgentListResponse)
async def get_agents():
    from clef_server.config import load_agent_configs
    path = _get_server_root() / "config" / "agents.yaml"
    configs = load_agent_configs(path)

    agents = []
    for name, cfg in configs.items():
        agents.append(AgentInfo(
            name=name,
            model_alias=cfg.model_alias,
            temperature=cfg.temperature,
            skills=cfg.skills,
            tools=cfg.tools,
        ))
    return AgentListResponse(agents=agents)


@router.put("/settings/agents", response_model=AgentListResponse)
async def update_agents(req: AgentUpdateRequest):
    from clef_server.config import AgentConfig, load_agent_configs, save_agent_configs
    path = _get_server_root() / "config" / "agents.yaml"
    configs = load_agent_configs(path)

    if req.agents:
        for name, updates in req.agents.items():
            if name not in configs:
                raise HTTPException(status_code=400, detail=f"Unknown agent: {name}")
            current = configs[name]
            configs[name] = AgentConfig(
                prompt_md=current.prompt_md,
                model_alias=updates.get("model_alias", current.model_alias),
                temperature=updates.get("temperature", current.temperature),
                skills=list(current.skills),
                tools=list(current.tools),
            )

    save_agent_configs(path, configs)
    return await get_agents()


@router.get("/settings/diagnostics")
async def get_diagnostics():
    server_root = _get_server_root()
    temp_workdir = Path(tempfile.gettempdir()) / "clef-work"

    total_size = 0
    session_count = 0
    if temp_workdir.exists():
        for p in temp_workdir.iterdir():
            if p.is_dir():
                session_count += 1
                total_size += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

    deps = []
    for pkg in ['music21', 'mido', 'yaml', 'fastapi', 'agent_framework']:
        try:
            importlib.import_module(pkg)
            deps.append({"name": pkg, "installed": True})
        except ImportError:
            deps.append({"name": pkg, "installed": False})

    return {
        "version": "0.2.0",
        "uptime_seconds": round(time.time() - _server_start_time),
        "temp_workdir": str(temp_workdir),
        "temp_session_count": session_count,
        "temp_disk_usage_mb": round(total_size / (1024 * 1024), 2),
        "dependencies": deps,
    }


@router.post("/settings/cleanup")
async def cleanup_old_sessions():
    temp_workdir = Path(tempfile.gettempdir()) / "clef-work"
    removed = 0
    if temp_workdir.exists():
        cutoff = time.time() - 86400  # 24 hours
        for p in temp_workdir.iterdir():
            if p.is_dir() and not p.is_symlink() and p.stat().st_mtime < cutoff:
                shutil.rmtree(p)
                removed += 1
    return {"removed_sessions": removed}
