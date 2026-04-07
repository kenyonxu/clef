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

WORKFLOW_STEPS = [
    {"id": 0, "name": "parse", "label": "Requirement Parsing"},
    {"id": 1, "name": "plan", "label": "Plan Generation"},
    {"id": 2, "name": "create", "label": "Full Creation"},
    {"id": 3, "name": "inject", "label": "Expression Injection"},
]


@dataclass
class ComposeSession:
    session_id: str
    workdir: str
    user_prompt: str = ""
    status: str = "created"
    plan: dict | None = None
    output_files: list[str] = field(default_factory=list)
    error: str | None = None
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

    def set_awaiting_confirm(self) -> None:
        self._transition("awaiting_confirm")

    def set_done(self, output_files: list[str] | None = None) -> None:
        if output_files:
            self.output_files = output_files
        self._transition("done")

    def set_failed(self, error: str) -> None:
        self.error = error
        self._transition("failed")

    def set_cancelled(self) -> None:
        self._transition("cancelled")

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
        """Return workflow steps with current status."""
        steps = []
        for s in WORKFLOW_STEPS:
            status = self.step_status.get(s["id"], "pending")
            step = {**s, "status": status}
            if hasattr(self, 'step_errors') and s["id"] in self.step_errors:
                step["error"] = self.step_errors[s["id"]]
            steps.append(step)
        return steps

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "user_prompt": self.user_prompt,
            "workdir": self.workdir,
            "output_files": self.output_files,
            "error": self.error,
            "workflow_steps": self.get_workflow_steps(),
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
