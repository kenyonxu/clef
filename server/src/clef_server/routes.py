"""FastAPI routes — 7 REST endpoints + SSE streaming."""

import json
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from clef_server.sessions import SessionManager

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
    output_files: list[str] = []
    error: str | None = None


class CancelResponse(BaseModel):
    session_id: str
    status: str


class SessionsResponse(BaseModel):
    sessions: list[dict]


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
    )
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
