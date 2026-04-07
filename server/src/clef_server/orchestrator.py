"""Compose orchestrator -- manages the 6-phase composition workflow.

Phase flow:
  parse (confirm) -> sample (confirm) -> create -> iterate -> review (confirm) -> express -> done
"""

import json
import logging
from pathlib import Path
from typing import Any

from agent_framework import Message

from clef_server.sessions import PHASES, PHASE_ORDER, SessionManager

logger = logging.getLogger(__name__)

# Re-export for convenience
__all__ = ["ComposeOrchestrator", "PHASE_ORDER"]


# Global session manager singleton (shared across routes/orchestrator)
_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    """Return the global SessionManager instance."""
    return _session_manager


class ComposeOrchestrator:
    """Drives a single compose session through the 6-phase workflow.

    Each phase method (`_phase_parse`, `_phase_sample`, etc.) is responsible for:
      1. Recording phase status via ``session.record_phase``
      2. Doing the actual work (LLM calls, tool invocations, file I/O)
      3. Calling ``_advance_phase`` when finished

    Phases with ``confirm=True`` in ``PHASES`` will cause the orchestrator to
    pause and set ``session.status = "awaiting_confirm"``.  The caller must
    invoke ``resume()`` to continue.
    """

    def __init__(
        self,
        session_id: str,
        providers: dict[str, Any],
        workdir: str,
    ) -> None:
        self.session_id = session_id
        self.providers = providers
        self.workdir = workdir

    # ------------------------------------------------------------------
    # Session access (always fresh from the manager)
    # ------------------------------------------------------------------

    @property
    def session(self):
        mgr = get_session_manager()
        session = mgr.get(self.session_id)
        if session is None:
            raise RuntimeError(f"Session {self.session_id} not found")
        return session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, prompt: str) -> None:
        """Begin the workflow -- runs Phase 0 (parse)."""
        self.session.set_running()
        await self._phase_parse(prompt)

    async def resume(self, user_feedback: str | None = None) -> None:
        """Resume from a confirmation checkpoint.

        Reads ``session.confirmation_data["phase"]`` to determine where to
        continue.  For the ``parse`` phase, we always advance to ``sample``
        regardless of feedback (the plan is accepted or regenerated inside
        ``_phase_sample``).
        """
        phase = self.session.confirmation_data.get("phase") if self.session.confirmation_data else None
        if phase is None:
            raise RuntimeError("Session is not awaiting confirmation")

        self.session.set_running()

        # H1: parse confirmation always advances to sample, no feedback loop
        if phase == "parse":
            await self._phase_sample(feedback=None)
            return

        # All other confirm phases: pass feedback through
        feedback = user_feedback
        phase_method = getattr(self, f"_phase_{phase}", None)
        if phase_method is not None:
            await phase_method(feedback=feedback)
        else:
            logger.warning("No phase method for %r after confirm, advancing", phase)
            await self._advance_phase(phase)

    # ------------------------------------------------------------------
    # Phase navigation helpers
    # ------------------------------------------------------------------

    def _next_phase(self, current: str) -> str | None:
        """Return the next phase ID after *current*, or ``None`` if at end."""
        try:
            idx = PHASE_ORDER.index(current)
        except ValueError:
            return None
        if idx + 1 < len(PHASE_ORDER):
            return PHASE_ORDER[idx + 1]
        return None

    def _phase_config(self, phase_id: str) -> dict:
        """Look up phase metadata by ID."""
        for p in PHASES:
            if p["id"] == phase_id:
                return p
        raise ValueError(f"Unknown phase: {phase_id}")

    async def _advance_phase(
        self,
        from_phase: str,
        confirmation_data: dict | None = None,
    ) -> None:
        """Transition from *from_phase* to the next phase.

        If the next phase has ``confirm=True``, sets the session to
        ``awaiting_confirm`` with *confirmation_data* and **returns** without
        running the phase method.  The caller (or user) must ``resume()`` later.

        For non-confirm phases, sets ``current_phase``, records "running", and
        immediately invokes the phase method.
        """
        next_id = self._next_phase(from_phase)
        if next_id is None:
            # Workflow complete
            self.session.set_done(output_files=self._collect_outputs())
            logger.info("Session %s: workflow complete", self.session_id)
            return

        config = self._phase_config(next_id)
        self.session.current_phase = next_id

        # C3: confirm phases must pause via set_awaiting_confirm
        if config.get("confirm", False):
            data = confirmation_data or {"phase": next_id}
            self.session.set_awaiting_confirm(confirmation_data=data)
            logger.info(
                "Session %s: awaiting confirm for phase %s",
                self.session_id,
                next_id,
            )
            return

        # Non-confirm: auto-run
        self.session.record_phase(next_id, "running")
        phase_method = getattr(self, f"_phase_{next_id}", None)
        if phase_method is not None:
            await phase_method()
        else:
            logger.warning("No implementation for phase %r, skipping", next_id)
            await self._advance_phase(next_id)

    # ------------------------------------------------------------------
    # Output collection
    # ------------------------------------------------------------------

    def _collect_outputs(self) -> list[str]:
        """Collect output file paths from ``workdir/output/``."""
        output_dir = Path(self.workdir) / "output"
        if not output_dir.exists():
            return []
        return [
            p.relative_to(Path(self.workdir)).as_posix()
            for p in sorted(output_dir.rglob("*"))
            if p.is_file()
        ]

    # ------------------------------------------------------------------
    # Phase 0: Parse + Plan
    # ------------------------------------------------------------------

    async def _phase_parse(self, prompt: str) -> None:
        """Phase 0: Parse requirements and generate plan.json via LLM."""
        client = next(iter(self.providers.values()), None)
        if not client:
            raise RuntimeError("No LLM provider available")

        self.session.record_phase("parse", "running")

        system_prompt = (
            "You are a music composition planner. Given a user's music description, "
            "generate a structured plan.json with these fields:\n"
            "- title: string\n"
            "- key: string (e.g. 'C', 'D', 'Bb')\n"
            "- scale: 'major' or 'minor'\n"
            "- bpm: integer\n"
            "- time_signature: string (e.g. '4/4')\n"
            "- form: string (e.g. 'ABA', 'AB', 'AABA')\n"
            "- sections: array of {id, name, measures, start_beat, energy_level, dynamics, balance_intent, melody_strategy}\n"
            "- orchestration: object with melody/harmony/bass/drums sub-objects, "
            "each having name, channel, instrument, range, register\n"
            "- generation_order: array like ['harmony', 'melody']\n"
            "- demo_length_bars: integer (2-16)\n\n"
            "Respond ONLY with valid JSON. No markdown, no explanation."
        )

        messages = [
            Message(role="system", contents=[system_prompt]),
            Message(role="user", contents=[prompt]),
        ]

        response = await client.get_response(messages)
        content = response.messages[0].contents[0] if response.messages else ""
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rstrip("`")

        plan = json.loads(content)

        # Persist plan.json to workdir
        plan_path = Path(self.workdir) / "plan.json"
        plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.session.record_phase("parse", "done")
        self.session.set_awaiting_confirm(confirmation_data={
            "phase": "parse",
            "title": "确认音乐规划",
            "plan": plan,
        })
        logger.info("Session %s: Phase 0 done, plan saved", self.session_id)

    # ------------------------------------------------------------------
    # Phase 1: Sample (方向小样) -- stub, implemented in Task 3
    # ------------------------------------------------------------------

    async def _phase_sample(self, feedback: str | None = None) -> None:
        """Phase 1: Generate direction sample for user confirmation."""
        ...

    # ------------------------------------------------------------------
    # Phase 2: Create (完整创作) -- stub, implemented in Task 4
    # ------------------------------------------------------------------

    async def _phase_create(self) -> None:
        """Phase 2: Full multi-agent composition."""
        ...

    # ------------------------------------------------------------------
    # Phase 3: Iterate (质量迭代) -- stub, implemented in Task 5
    # ------------------------------------------------------------------

    async def _phase_iterate(self) -> None:
        """Phase 3: Review-driven iteration (up to N rounds)."""
        ...

    # ------------------------------------------------------------------
    # Phase 4: Review (试听审核) -- stub, implemented in Task 5
    # ------------------------------------------------------------------

    async def _phase_review(self, feedback: str | None = None) -> None:
        """Phase 4: User listens and confirms or requests changes."""
        ...

    # ------------------------------------------------------------------
    # Phase 5: Express (表现力注入) -- stub, implemented in Task 6
    # ------------------------------------------------------------------

    async def _phase_express(self) -> None:
        """Phase 5: Inject CC/pitch-bend/vibrato expression data."""
        ...
