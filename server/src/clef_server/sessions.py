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


@dataclass
class ComposeSession:
    session_id: str
    workdir: str
    user_prompt: str = ""
    status: str = "created"
    plan: dict | None = None
    output_files: list[str] = field(default_factory=list)
    error: str | None = None
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

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "user_prompt": self.user_prompt,
            "workdir": self.workdir,
            "output_files": self.output_files,
            "error": self.error,
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
