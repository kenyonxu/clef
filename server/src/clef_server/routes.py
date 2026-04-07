"""FastAPI routes — 7 REST endpoints + SSE streaming."""

import asyncio
import json
import logging
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
    action: str = Field(..., description="'continue' or 'cancel'")
    feedback: str | None = Field(None, description="Optional user feedback text")


# === Workflow Execution ===

async def _run_workflow(session_id: str, prompt: str, plan: dict | None, workdir: str) -> None:
    """Start the compose workflow via orchestrator."""
    session = _session_manager.get(session_id)
    if not session:
        logger.error(f"Session {session_id} not found")
        return

    try:
        from clef_server.config import load_provider_config
        from clef_server.providers import create_providers
        from clef_server.orchestrator import ComposeOrchestrator

        server_root = Path(__file__).resolve().parent.parent.parent
        provider_config = load_provider_config(server_root / "config" / "providers.yaml")
        providers = create_providers(provider_config)

        orchestrator = ComposeOrchestrator(session_id=session_id, providers=providers, workdir=workdir)
        await orchestrator.start(prompt)

    except Exception as e:
        logger.exception(f"Session {session_id}: workflow failed")
        session.set_failed(error=str(e))


# === Endpoints ===

@router.post("/compose", response_model=ComposeResponse)
async def create_compose(req: ComposeRequest):
    session_id = f"clef-{uuid.uuid4().hex[:8]}"
    workdir = str(Path(tempfile.gettempdir()) / "clef-work" / session_id)
    Path(workdir).mkdir(parents=True, exist_ok=True)
    (Path(workdir) / "output").mkdir(exist_ok=True)
    session = _session_manager.create(
        user_prompt=req.prompt,
        workdir=workdir,
        plan=req.plan,
        session_id=session_id,
    )
    task = asyncio.create_task(_run_workflow(session_id, req.prompt, req.plan, workdir))
    task.add_done_callback(lambda t: t.exception() and logger.error(f"Workflow task failed: {t.exception()}"))
    return ComposeResponse(session_id=session.session_id, status=session.status)


@router.get("/status/{session_id}", response_model=StatusResponse)
async def get_status(session_id: str):
    session = _session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return StatusResponse(
        session_id=session.session_id,
        status=session.status,
        user_prompt=session.user_prompt,
        workflow_steps=session.get_workflow_steps(),
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
        async def event_generator():
            yield {"event": "connected", "data": json.dumps({"session_id": session_id})}
        return EventSourceResponse(event_generator())
    except ImportError:
        raise HTTPException(status_code=503, detail="SSE not available (sse-starlette not installed)")


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

    # action == "continue"
    try:
        from clef_server.config import load_provider_config
        from clef_server.providers import create_providers
        from clef_server.orchestrator import ComposeOrchestrator

        server_root = Path(__file__).resolve().parent.parent.parent
        provider_config = load_provider_config(server_root / "config" / "providers.yaml")
        providers = create_providers(provider_config)

        orchestrator = ComposeOrchestrator(session_id=session_id, providers=providers, workdir=session.workdir)
        await orchestrator.resume(req.feedback)
    except Exception as e:
        logger.exception(f"Session {session_id}: resume failed")
        session.set_failed(error=str(e))

    return {"session_id": session.session_id, "status": session.status, "current_phase": session.current_phase}


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
