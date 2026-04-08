"""Session management — lifecycle tracking for compose jobs."""

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path


VALID_TRANSITIONS = {
    "created": {"running", "cancelled"},
    "running": {"done", "failed", "cancelled", "awaiting_confirm"},
    "awaiting_confirm": {"running", "cancelled"},
    "done": set(),
    "failed": set(),
    "cancelled": set(),
}

# Legacy 4-step numeric workflow — kept for backward compatibility (routes.py)
WORKFLOW_STEPS = [
    {"id": 0, "name": "parse", "label": "Requirement Parsing"},
    {"id": 1, "name": "plan", "label": "Plan Generation"},
    {"id": 2, "name": "create", "label": "Full Creation"},
    {"id": 3, "name": "inject", "label": "Expression Injection"},
]

PHASES = [
    {"id": "parse",   "label": "需求解析 + 规划",  "confirm": True,  "agents": []},
    {"id": "sample",  "label": "方向小样",         "confirm": True,  "agents": ["clef-composer", "clef-harmonist", "clef-rhythmist"]},
    {"id": "create",  "label": "完整创作",         "confirm": False, "agents": ["clef-composer", "clef-harmonist", "clef-rhythmist"]},
    {"id": "iterate", "label": "质量迭代",         "confirm": False, "agents": ["clef-reviewer", "clef-revision"]},
    {"id": "review",  "label": "试听审核",         "confirm": True,  "agents": ["clef-reviewer"]},
    {"id": "express", "label": "表现力注入",       "confirm": False, "agents": ["clef-orchestrator"]},
]

PHASE_ORDER = ["parse", "sample", "create", "iterate", "review", "express"]


@dataclass
class ComposeSession:
    session_id: str
    workdir: str
    user_prompt: str = ""
    status: str = "created"
    plan: dict | None = None
    output_files: list[str] = field(default_factory=list)
    error: str | None = None
    current_phase: str = "parse"
    confirmation_data: dict | None = None
    phase_history: list[dict] = field(default_factory=list)
    sample_round: int = 0
    iteration_count: int = 0
    step_status: dict[int, str] = field(default_factory=lambda: {0: "pending", 1: "pending", 2: "pending", 3: "pending"})
    current_step: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def _transition(self, new_status: str) -> None:
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{self.status}' to '{new_status}'. "
                f"Allowed: {allowed}"
            )
        self.status = new_status
        self.updated_at = time.time()

    def set_running(self) -> None:
        self._transition("running")

    def set_awaiting_confirm(self, confirmation_data: dict | None = None) -> None:
        self._transition("awaiting_confirm")
        self.confirmation_data = confirmation_data

    def set_done(self, output_files: list[str] | None = None) -> None:
        if output_files:
            self.output_files = output_files
        self._transition("done")

    def set_failed(self, error: str) -> None:
        self.error = error
        self._transition("failed")

    def set_cancelled(self) -> None:
        self._transition("cancelled")

    def record_phase(self, phase_id: str, status: str, *, error: str | None = None) -> None:
        entry = {"phase": phase_id, "status": status, "error": error, "timestamp": time.time()}
        self.phase_history.append(entry)
        self.updated_at = time.time()

    def update_step(self, step_id: int, status: str, *, error: str | None = None) -> None:
        """Update a workflow step's status."""
        self.step_status[step_id] = status
        self.updated_at = time.time()
        if error:
            self.step_errors = getattr(self, 'step_errors', {})
            self.step_errors[step_id] = error

    def advance_step(self, step_id: int) -> None:
        """Mark step as done and advance to next."""
        self.step_status[step_id] = "done"
        if step_id + 1 < len(WORKFLOW_STEPS):
            self.current_step = step_id + 1
            self.step_status[step_id + 1] = "running"
        self.updated_at = time.time()

    def get_workflow_steps(self) -> list[dict]:
        """Return workflow phases with current status derived from phase_history."""
        phases = []
        for p in PHASES:
            status = "pending"
            error = None
            for entry in reversed(self.phase_history):
                if entry["phase"] == p["id"]:
                    status = entry["status"]
                    error = entry.get("error")
                    break
            step = {**p, "status": status}
            if error is not None:
                step["error"] = error
            phases.append(step)
        return phases

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "user_prompt": self.user_prompt,
            "workdir": self.workdir,
            "output_files": self.output_files,
            "error": self.error,
            "workflow_steps": self.get_workflow_steps(),
            "current_phase": self.current_phase,
            "confirmation_data": self.confirmation_data,
            "phase_history": self.phase_history,
            "sample_round": self.sample_round,
            "iteration_count": self.iteration_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SessionManager:
    """In-memory session store."""

    def __init__(self):
        self._sessions: dict[str, ComposeSession] = {}

    def create(self, user_prompt: str, workdir: str, plan: dict | None = None, session_id: str | None = None) -> ComposeSession:
        if session_id is None:
            session_id = f"clef-{uuid.uuid4().hex[:8]}"
        session = ComposeSession(
            session_id=session_id,
            workdir=workdir,
            user_prompt=user_prompt,
            plan=plan,
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> ComposeSession | None:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[ComposeSession]:
        return list(self._sessions.values())

    def remove(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
