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

logger = logging.getLogger(__name__)

router = APIRouter()
_session_manager = SessionManager()


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


class CancelResponse(BaseModel):
    session_id: str
    status: str


class SessionsResponse(BaseModel):
    sessions: list[dict]


# === Workflow Execution ===

async def _run_workflow(session_id: str, prompt: str, plan: dict | None, workdir: str) -> None:
    """Run the compose workflow in the background, updating session state."""
    session = _session_manager.get(session_id)
    if not session:
        logger.error(f"Session {session_id} not found")
        return

    try:
        session.set_running()
        logger.info(f"Session {session_id}: workflow started")

        from clef_server.config import load_provider_config, load_agent_configs
        from clef_server.providers import create_providers
        from clef_server.workflow import build_compose_workflow, ComposeRequest

        server_root = Path(__file__).resolve().parent.parent.parent
        provider_config = load_provider_config(
            server_root / "config" / "providers.yaml"
        )
        providers = create_providers(provider_config)

        workflow = build_compose_workflow(
            providers=providers,
            plan=plan,
            workdir=workdir,
        )

        request = ComposeRequest(user_prompt=prompt, workdir=workdir, plan=plan)
        result = await workflow.run(request)
        outputs = result.get_outputs()

        output_files = [f for f in outputs if isinstance(f, str)]
        session.set_done(output_files=output_files)
        logger.info(f"Session {session_id}: workflow done, outputs={output_files}")

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
async def confirm_sample(session_id: str):
    session = _session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "awaiting_confirm":
        raise HTTPException(status_code=400, detail="Session is not awaiting confirmation")
    session.set_running()
    return {"session_id": session.session_id, "status": "running"}


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
