"""Session management — lifecycle tracking for compose jobs."""

import asyncio
import json
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

TERMINAL_STATES = frozenset({"done", "failed", "cancelled"})


@dataclass
class ToolPermissions:
    """Per-session tool permission overrides: deny > override > base."""
    denied_tools: frozenset[str] = frozenset()
    allowed_overrides: frozenset[str] = frozenset()

    def is_tool_allowed(self, tool: str, agent: str, base_map: dict[str, list[str]]) -> bool:
        if tool in self.denied_tools:
            return False
        if tool in self.allowed_overrides:
            return True
        return tool in base_map.get(agent, [])

# Legacy 4-step numeric workflow — kept for backward compatibility (routes.py)
WORKFLOW_STEPS = [
    {"id": 0, "name": "parse", "label": "Requirement Parsing"},
    {"id": 1, "name": "plan", "label": "Plan Generation"},
    {"id": 2, "name": "create", "label": "Full Creation"},
    {"id": 3, "name": "inject", "label": "Expression Injection"},
]

PHASES = [
    {"id": "parse",   "label": "需求解析 + 规划",  "confirm": True,  "agents": []},
    {"id": "sample",  "label": "方向小样",         "confirm": True,  "agents": ["clef-composer", "clef-harmonist", "clef-rhythmist", "clef-reviewer"]},
    {"id": "create",  "label": "完整创作",         "confirm": False, "agents": ["clef-composer", "clef-harmonist", "clef-rhythmist"]},
    {"id": "iterate", "label": "质量迭代",         "confirm": False, "agents": ["clef-reviewer", "clef-leader", "clef-revision"]},
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
    profile: str | None = None
    output_files: list[str] = field(default_factory=list)
    error: str | None = None
    current_phase: str = "parse"
    confirmation_data: dict | None = None
    phase_history: list[dict] = field(default_factory=list)
    sample_round: int = 0
    iteration_count: int = 0
    sub_steps: list[dict] = field(default_factory=list)
    _event_queues: list[asyncio.Queue] = field(default_factory=list)
    step_status: dict[int, str] = field(default_factory=lambda: {0: "pending", 1: "pending", 2: "pending", 3: "pending"})
    current_step: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    _cancel_requested: bool = False
    tool_permissions: ToolPermissions = field(default_factory=ToolPermissions)

    @property
    def is_terminal(self) -> bool:
        """True if session is in a terminal state (done/failed/cancelled)."""
        return self.status in TERMINAL_STATES

    @property
    def cancel_requested(self) -> bool:
        """True if cancellation has been requested."""
        return self._cancel_requested

    def request_cancel(self) -> None:
        """Mark cancellation intent. Allows current phase to complete."""
        if self.is_terminal:
            return
        self._cancel_requested = True
        self.updated_at = time.time()

    def _transition(self, new_status: str) -> None:
        if self.is_terminal:
            raise ValueError(
                f"Session is terminal ({self.status}), cannot transition to {new_status}"
            )
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
        # Clear sub-steps when a phase starts running
        if status == "running":
            self.current_phase = phase_id
            self.sub_steps = []

    def record_sub_step(self, label: str, status: str, *, agent: str | None = None) -> None:
        """Record a sub-step within the current phase and emit SSE event."""
        entry = {
            "label": label,
            "status": status,
            "agent": agent,
            "phase": self.current_phase,
            "timestamp": time.time(),
        }
        # Update or append in sub_steps list
        for i, existing in enumerate(self.sub_steps):
            if existing["label"] == label and existing["phase"] == self.current_phase:
                self.sub_steps[i] = entry
                break
        else:
            self.sub_steps.append(entry)
        self.updated_at = time.time()

        # Emit to all SSE listeners
        event_data = json.dumps(entry, ensure_ascii=False)
        for q in self._event_queues:
            try:
                q.put_nowait({"event": f"sub_step_{status}", "data": event_data})
            except asyncio.QueueFull:
                pass  # Drop event if queue is full

    def add_event_listener(self, queue) -> None:
        """Register an asyncio.Queue for SSE event delivery."""
        self._event_queues.append(queue)

    def remove_event_listener(self, queue) -> None:
        """Unregister an SSE event listener."""
        try:
            self._event_queues.remove(queue)
        except ValueError:
            pass

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
            # Include sub-steps for the current phase
            if p["id"] == self.current_phase and self.sub_steps:
                step["sub_steps"] = list(self.sub_steps)
            phases.append(step)
        return phases

    def to_dict(self) -> dict:
        """Serialize for API responses (includes derived fields)."""
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

    def to_persist_dict(self) -> dict:
        """Serialize session for disk persistence (excludes runtime state)."""
        return {
            "session_id": self.session_id,
            "status": self.status,
            "user_prompt": self.user_prompt,
            "workdir": self.workdir,
            "plan": self.plan,
            "profile": self.profile,
            "output_files": self.output_files,
            "error": self.error,
            "current_phase": self.current_phase,
            "confirmation_data": self.confirmation_data,
            "phase_history": self.phase_history,
            "sub_steps": self.sub_steps,
            "sample_round": self.sample_round,
            "iteration_count": self.iteration_count,
            "step_status": self.step_status,
            "current_step": self.current_step,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ComposeSession":
        """Reconstruct a session from serialized dict (excludes runtime state)."""
        return cls(
            session_id=data["session_id"],
            workdir=data.get("workdir", ""),
            user_prompt=data.get("user_prompt", ""),
            status=data.get("status", "created"),
            plan=data.get("plan"),
            profile=data.get("profile"),
            output_files=data.get("output_files", []),
            error=data.get("error"),
            current_phase=data.get("current_phase", "parse"),
            confirmation_data=data.get("confirmation_data"),
            phase_history=data.get("phase_history", []),
            sub_steps=data.get("sub_steps", []),
            iteration_count=data.get("iteration_count", 0),
            sample_round=data.get("sample_round", 0),
            step_status=data.get("step_status", {0: "pending", 1: "pending", 2: "pending", 3: "pending"}),
            current_step=data.get("current_step", 0),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


def _validate_session_id(session_id: str) -> str:
    """Sanitize session_id to prevent path traversal in file operations."""
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        raise ValueError(f"Invalid session_id: {session_id!r}")
    return session_id


class SessionManager:
    """In-memory session store with optional TTL and disk persistence."""

    def __init__(self, ttl_seconds: float | None = None, persist_dir: str | None = None) -> None:
        self._sessions: dict[str, ComposeSession] = {}
        self._ttl_seconds = ttl_seconds
        self._persist_dir: Path | None = Path(persist_dir) if persist_dir else None

    def create(self, user_prompt: str, workdir: str, plan: dict | None = None, session_id: str | None = None, profile: str | None = None) -> ComposeSession:
        if session_id is None:
            session_id = f"clef-{uuid.uuid4().hex[:8]}"
        session = ComposeSession(
            session_id=session_id,
            workdir=workdir,
            user_prompt=user_prompt,
            plan=plan,
            profile=profile,
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> ComposeSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if self._ttl_seconds is not None:
            age = time.time() - session.created_at
            if age > self._ttl_seconds:
                del self._sessions[session_id]
                return None
        return session

    def list_sessions(self) -> list[ComposeSession]:
        return list(self._sessions.values())

    def persist(self, session: ComposeSession) -> None:
        """Save session state to disk."""
        if not self._persist_dir:
            return
        _validate_session_id(session.session_id)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        path = self._persist_dir / f"{session.session_id}.json"
        path.write_text(json.dumps(session.to_persist_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def restore(self, session_id: str) -> ComposeSession | None:
        """Load session from disk."""
        if not self._persist_dir:
            return None
        _validate_session_id(session_id)
        path = self._persist_dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            session = ComposeSession.from_dict(data)
            self._sessions[session_id] = session
            return session
        except (json.JSONDecodeError, KeyError, OSError) as e:
            import logging
            logging.getLogger(__name__).warning("Failed to restore session %s: %s", session_id, e)
            return None

    def restore_all_incomplete(self) -> list[ComposeSession]:
        """Restore all non-terminal sessions from disk."""
        if not self._persist_dir:
            return []
        results = []
        for path in self._persist_dir.glob("clef-*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                session = ComposeSession.from_dict(data)
                if not session.is_terminal:
                    self._sessions[session.session_id] = session
                    results.append(session)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                import logging
                logging.getLogger(__name__).warning("Failed to restore session from %s: %s", path, e)
        return results

    def save(self, session: ComposeSession) -> None:
        """Persist session if persistence is enabled. Alias for persist()."""
        self.persist(session)

    def configure_persistence(self, persist_dir: str) -> None:
        """Configure or update the persistence directory."""
        self._persist_dir = Path(persist_dir)

    def remove(self, session_id: str) -> bool:
        was_in_memory = session_id in self._sessions
        if was_in_memory:
            del self._sessions[session_id]
        removed_disk = False
        if self._persist_dir:
            _validate_session_id(session_id)
            path = self._persist_dir / f"{session_id}.json"
            if path.exists():
                path.unlink()
                removed_disk = True
        return was_in_memory or removed_disk
