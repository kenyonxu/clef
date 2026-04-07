"""Compose orchestrator -- manages the 6-phase composition workflow.

Phase flow:
  parse (confirm) -> sample (confirm) -> create -> iterate -> review (confirm) -> express -> done
"""

import json
import logging
import re
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

    # Maximum retry / iteration counts
    MAX_MELODY_GATE_RETRIES = 3
    MAX_ITERATION_ROUNDS = 3

    # Voice label mapping: role -> ABC voice number
    VOICE_MAP = {"melody": "V:1", "harmony": "V:2", "rhythm": "V:3+V:4"}

    # Agent config key -> agent factory name in agents.yaml
    VOICE_AGENT_MAP = {"melody": "clef-composer", "harmony": "clef-harmonist", "rhythm": "clef-rhythmist"}

    def __init__(
        self,
        session_id: str,
        providers: dict[str, Any],
        workdir: str,
    ) -> None:
        self.session_id = session_id
        self.providers = providers
        self.workdir = workdir
        # Resolve project root (where .claude/agents/ lives)
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent

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

        # Review phase: user feedback triggers iteration, no feedback advances to express
        if phase == "review":
            if user_feedback:
                await self._phase_iterate(extra_feedback=user_feedback)
            else:
                await self._phase_express()
            return

        # All other confirm phases: pass feedback through
        phase_method = getattr(self, f"_phase_{phase}", None)
        if phase_method is not None:
            await phase_method(feedback=user_feedback)
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
        content = str(response.messages[0].contents[0]) if response.messages else ""
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rstrip("`")

        try:
            plan = json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"LLM returned invalid plan JSON: {e}") from e

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
    # Agent execution helpers
    # ------------------------------------------------------------------

    # Agent definitions: prompt file, model alias, skills
    _AGENT_DEFS: dict[str, dict[str, Any]] = {
        "clef-composer": {
            "prompt_md": "clef-composer.md",
            "model_alias": "deepseek",
            "skills": ["melody", "orchestration", "abc"],
        },
        "clef-harmonist": {
            "prompt_md": "clef-harmonist.md",
            "model_alias": "deepseek",
            "skills": ["harmony", "abc"],
        },
        "clef-rhythmist": {
            "prompt_md": "clef-rhythmist.md",
            "model_alias": "deepseek",
            "skills": ["rhythm", "abc"],
        },
        "clef-reviewer": {
            "prompt_md": "clef-reviewer.md",
            "model_alias": "deepseek",
            "skills": ["structure", "orchestration", "abc"],
        },
        "clef-orchestrator": {
            "prompt_md": "clef-orchestrator.md",
            "model_alias": "deepseek",
            "skills": ["orchestration", "abc"],
        },
    }

    async def _run_agent(
        self,
        agent_name: str,
        message: str,
        plan: dict | None = None,
        score_abc: str | None = None,
    ) -> str:
        """Run an agent by building its system prompt and calling LLM directly.

        Bypasses AF AgentExecutor (which requires WorkflowContext) and
        uses ChatCompletionsClient with the agent's instructions + skills.
        """
        agent_def = self._AGENT_DEFS.get(agent_name)
        if not agent_def:
            logger.warning("Unknown agent %s, returning placeholder", agent_name)
            return f"[placeholder ABC for {agent_name}]"

        try:
            from clef_server.agents import _build_instructions
            from clef_server.middleware import ClefContextMiddleware

            # Build system prompt from agent markdown + skills + context
            prompt_path = self.project_root / ".claude" / "agents" / agent_def["prompt_md"]
            if not prompt_path.exists():
                logger.warning("Agent prompt not found: %s", prompt_path)
                return f"[placeholder ABC for {agent_name}]"

            skills_dir = self.project_root / ".claude" / "skills" / "clef-compose"
            middleware = ClefContextMiddleware(
                skills=agent_def["skills"],
                skills_dir=skills_dir,
            )
            instructions = _build_instructions(
                prompt_md=prompt_path,
                middleware=middleware,
                plan=plan,
                score_abc=score_abc,
                workdir=self.workdir,
            )

            # Get LLM client (resolve model_alias, fall back to first available)
            model_alias = agent_def["model_alias"]
            client = self.providers.get(model_alias) or next(iter(self.providers.values()), None)
            if not client:
                raise RuntimeError(f"No LLM client available for {agent_name} (alias={model_alias})")

            # Call LLM with system prompt + user message
            messages = [
                Message(role="system", contents=[instructions]),
                Message(role="user", contents=[message]),
            ]
            response = await client.get_response(messages)

            # Extract text from response
            content = ""
            if response.messages and response.messages[0].contents:
                content = str(response.messages[0].contents[0])
            return content
        except Exception as exc:
            logger.error("Agent %s execution failed: %s", agent_name, exc)
            raise RuntimeError(f"Agent {agent_name} failed: {exc}") from exc

    def _extract_abc(self, text: str) -> str:
        """Extract ABC notation from agent response text.

        Handles markdown code fences (```abc ... ```) or raw ABC content.
        """
        text = text.strip()
        # Try fenced block first
        fence_match = re.search(r"```(?:abc)?\s*\n(.*?)```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()
        # Fallback: treat entire text as ABC if it looks like ABC
        if text.startswith("X:") or text.startswith("T:"):
            return text
        return text

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from agent response, handling markdown fencing."""
        text = text.strip()
        fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text, "verdict": "pass"}

    # ------------------------------------------------------------------
    # Reviewer helper
    # ------------------------------------------------------------------

    async def _call_reviewer(
        self,
        plan: dict,
        melody_only: bool = False,
        extra_context: str = "",
    ) -> dict:
        """Run the reviewer agent and return a review dict.

        Returns {"verdict": "pass"|"revise", ...} or a fallback dict on parse failure.
        """
        score_path = Path(self.workdir) / "score.abc"
        score_text = score_path.read_text(encoding="utf-8") if score_path.exists() else ""

        scope = "melody only" if melody_only else "full composition"
        message = (
            f"Review the following ABC score ({scope}):\n\n"
            f"Score:\n```\n{score_text}\n```\n\n"
            f"Plan:\n```json\n{json.dumps(plan, indent=2)}\n```\n\n"
            f"Respond with a JSON object containing at minimum:\n"
            f'- "verdict": "pass" or "revise"\n'
            f'- "issues": array of issue descriptions\n'
            f'- "score": overall quality score 1-10\n'
        )
        if extra_context:
            message += f"\nAdditional context: {extra_context}\n"

        response_text = await self._run_agent("clef-reviewer", message, plan=plan, score_abc=score_text)
        return self._extract_json(response_text)

    # ------------------------------------------------------------------
    # Leader helper
    # ------------------------------------------------------------------

    async def _call_leader(
        self,
        plan: dict,
        review: dict,
        extra_feedback: str | None = None,
    ) -> dict:
        """Run the leader agent to decide iteration tasks.

        Returns {"iteration_complete": bool, "tasks": [...]} or a fallback.
        """
        score_path = Path(self.workdir) / "score.abc"
        score_text = score_path.read_text(encoding="utf-8") if score_path.exists() else ""

        message = (
            f"Based on this review, decide what needs to be revised:\n\n"
            f"Review:\n```json\n{json.dumps(review, indent=2)}\n```\n\n"
            f"Score:\n```\n{score_text}\n```\n\n"
            f"Respond with a JSON object:\n"
            f'- "iteration_complete": true if no more work needed\n'
            f'- "tasks": array of {{agent, voice, depends_on, instruction}}\n'
        )
        if extra_feedback:
            message += f"\nUser feedback: {extra_feedback}\n"

        response_text = await self._run_agent("clef-orchestrator", message, plan=plan, score_abc=score_text)
        return self._extract_json(response_text)

    # ------------------------------------------------------------------
    # Phase 1: Sample (方向小样)
    # ------------------------------------------------------------------

    async def _phase_sample(self, feedback: str | None = None) -> None:
        """Phase 1: Generate direction sample for user confirmation."""
        self.session.current_phase = "sample"
        self.session.record_phase("sample", "running")

        plan_path = Path(self.workdir) / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        score_path = Path(self.workdir) / "score.abc"

        generation_order = plan.get("generation_order", ["harmony", "melody"])
        fragments: dict[str, str] = {}
        abc_parts: list[str] = []

        # Step 1: Generate voice parts in generation_order
        for voice in generation_order:
            agent_name = self.VOICE_AGENT_MAP.get(voice)
            if not agent_name:
                continue
            voice_label = self.VOICE_MAP.get(voice, f"V:{voice}")
            demo_bars = plan.get("demo_length_bars", 4)

            message = (
                f"Generate a {demo_bars}-bar {voice} part as ABC notation. "
                f"Use voice label {voice_label}. Key: {plan.get('key', 'C')}, "
                f"Scale: {plan.get('scale', 'major')}, "
                f"Time: {plan.get('time_signature', '4/4')}, "
                f"BPM: {plan.get('bpm', 120)}. "
                f"This is a direction sample — focus on establishing the musical character. "
                f"Output only ABC notation."
            )

            response = await self._run_agent(agent_name, message, plan=plan)
            abc_text = self._extract_abc(response)
            fragments[voice_label] = abc_text
            abc_parts.append(f"{voice_label}\n{abc_text}")

        # C1/C2: merge_abc takes positional (plan, fragments, output), returns dict (side-effect)
        from clef_server.tools import merge_abc
        merge_result = merge_abc(str(plan_path), fragments, str(score_path))
        if "error" in merge_result:
            logger.error("merge_abc failed: %s", merge_result["error"])
            raise RuntimeError(f"merge_abc failed: {merge_result['error']}")

        # Step 2: Melody gate — review melody only up to 3 times
        melody_agent = self.VOICE_AGENT_MAP.get("melody", "clef-composer")
        melody_label = self.VOICE_MAP.get("melody", "V:1")
        for _ in range(self.MAX_MELODY_GATE_RETRIES):
            review = await self._call_reviewer(plan, melody_only=True)
            if review.get("verdict") != "revise":
                break

            issues = review.get("issues", [])
            feedback_msg = "Issues found:\n" + "\n".join(f"- {i}" for i in issues)
            response = await self._run_agent(
                melody_agent,
                f"Revise the melody based on feedback:\n{feedback_msg}\n\nOutput only the revised ABC.",
                plan=plan,
                score_abc=score_path.read_text(encoding="utf-8") if score_path.exists() else "",
            )
            abc_text = self._extract_abc(response)
            fragments[melody_label] = abc_text
            merge_result = merge_abc(str(plan_path), fragments, str(score_path))
            if "error" in merge_result:
                logger.error("merge_abc (melody gate) failed: %s", merge_result["error"])
                raise RuntimeError(f"merge_abc (melody gate) failed: {merge_result['error']}")

        # Step 3: Convert sample to MIDI
        sample_mid = Path(self.workdir) / "sample.mid"
        from clef_server.tools import abc_to_midi
        midi_result = abc_to_midi(str(score_path), str(sample_mid))
        if "error" in midi_result:
            logger.error("abc_to_midi failed: %s", midi_result["error"])
            raise RuntimeError(f"abc_to_midi failed: {midi_result['error']}")

        # Step 4: Full review for confirmation data
        full_review = await self._call_reviewer(plan, melody_only=False)

        self.session.record_phase("sample", "done")
        self.session.set_awaiting_confirm(confirmation_data={
            "phase": "sample",
            "title": "试听方向小样",
            "sample_file": str(sample_mid.name),
            "review": full_review,
            "sample_round": self.session.sample_round,
        })
        logger.info("Session %s: Phase 1 (sample) done", self.session_id)

    # ------------------------------------------------------------------
    # Phase 2: Create (完整创作)
    # ------------------------------------------------------------------

    async def _phase_create(self) -> None:
        """Phase 2: Full multi-agent composition."""
        self.session.record_phase("create", "running")

        plan_path = Path(self.workdir) / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        score_path = Path(self.workdir) / "score.abc"

        fragments: dict[str, str] = {}

        # Generate all 3 voices: harmony, melody, rhythm
        for voice in ["harmony", "melody", "rhythm"]:
            agent_name = self.VOICE_AGENT_MAP.get(voice)
            if not agent_name:
                continue
            voice_label = self.VOICE_MAP.get(voice, f"V:{voice}")

            message = (
                f"Generate the full {voice} part as ABC notation. "
                f"Use voice label {voice_label}. Key: {plan.get('key', 'C')}, "
                f"Scale: {plan.get('scale', 'major')}, "
                f"Time: {plan.get('time_signature', '4/4')}, "
                f"BPM: {plan.get('bpm', 120)}, "
                f"Form: {plan.get('form', 'ABA')}. "
                f"Output only ABC notation."
            )

            response = await self._run_agent(agent_name, message, plan=plan)
            abc_text = self._extract_abc(response)
            fragments[voice_label] = abc_text

        # Merge all fragments
        from clef_server.tools import merge_abc
        merge_result = merge_abc(str(plan_path), fragments, str(score_path))
        if "error" in merge_result:
            logger.error("merge_abc failed: %s", merge_result["error"])
            raise RuntimeError(f"merge_abc failed: {merge_result['error']}")

        # Validate
        report_path = Path(self.workdir) / "validation_report.json"
        from clef_server.tools import validate_abc
        validate_result = validate_abc(str(score_path), str(plan_path), str(report_path))
        if "error" in validate_result:
            logger.error("validate_abc failed: %s", validate_result["error"])

        # Convert to MIDI
        base_mid = Path(self.workdir) / "base.mid"
        from clef_server.tools import abc_to_midi
        midi_result = abc_to_midi(str(score_path), str(base_mid))
        if "error" in midi_result:
            logger.error("abc_to_midi failed: %s", midi_result["error"])
            raise RuntimeError(f"abc_to_midi failed: {midi_result['error']}")

        self.session.record_phase("create", "done")
        logger.info("Session %s: Phase 2 (create) done", self.session_id)

        # Auto-advance to Phase 3 (iterate, non-confirm)
        await self._advance_phase("create")

    # ------------------------------------------------------------------
    # Phase 3: Iterate (质量迭代)
    # ------------------------------------------------------------------

    async def _phase_iterate(self, extra_feedback: str | None = None) -> None:
        """Phase 3: Review-driven iteration (up to N rounds)."""
        self.session.record_phase("iterate", "running")

        plan_path = Path(self.workdir) / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        score_path = Path(self.workdir) / "score.abc"

        for round_num in range(1, self.MAX_ITERATION_ROUNDS + 1):
            self.session.iteration_count = round_num

            # Full review
            review = await self._call_reviewer(plan, melody_only=False)

            # Leader decides tasks
            leader_decision = await self._call_leader(plan, review, extra_feedback=extra_feedback)
            tasks = leader_decision.get("tasks", [])

            if leader_decision.get("iteration_complete", False) or not tasks:
                logger.info(
                    "Session %s: iteration round %d — no tasks, stopping",
                    self.session_id, round_num,
                )
                break

            # Sort by depends_on for execution order
            completed_agents: set[str] = set()
            tasks_sorted = sorted(tasks, key=lambda t: t.get("depends_on", ""))
            for task in tasks_sorted:
                dep = task.get("depends_on", "")
                if dep and dep not in completed_agents:
                    continue  # skip if dependency not yet completed

                agent_name = task.get("agent", "clef-composer")
                instruction = task.get("instruction", "Revise based on review feedback.")

                current_score = score_path.read_text(encoding="utf-8") if score_path.exists() else ""
                response = await self._run_agent(
                    agent_name,
                    instruction,
                    plan=plan,
                    score_abc=current_score,
                )
                abc_text = self._extract_abc(response)

                voice = task.get("voice", "melody")
                voice_label = self.VOICE_MAP.get(voice, f"V:{voice}")

                # Agent writes directly to score.abc — H7: do NOT call merge_abc with empty fragments
                # Update score by appending the revised part
                score_path.write_text(
                    current_score + f"\n% --- Iteration {round_num}: {agent_name} ({voice}) ---\n{voice_label}\n{abc_text}\n",
                    encoding="utf-8",
                )
                completed_agents.add(agent_name)

            # Validate after each iteration round
            report_path = Path(self.workdir) / f"validation_report_iter{round_num}.json"
            from clef_server.tools import validate_abc
            validate_abc(str(score_path), str(plan_path), str(report_path))

        # C6: Set confirmation_data with review + iteration count before advancing
        final_review = await self._call_reviewer(plan, melody_only=False)
        confirmation_data = {
            "phase": "review",
            "title": "试听审核",
            "review": final_review,
            "iteration_count": self.session.iteration_count,
            "output_file": "output/final.mid",
        }

        self.session.record_phase("iterate", "done")
        logger.info(
            "Session %s: Phase 3 (iterate) done, %d rounds",
            self.session_id, self.session.iteration_count,
        )

        # Advance to review (confirm phase)
        await self._advance_phase("iterate", confirmation_data=confirmation_data)

    # ------------------------------------------------------------------
    # Phase 4: Express (表现力注入)
    # ------------------------------------------------------------------

    async def _phase_express(self) -> None:
        """Phase 4: Inject CC/pitch-bend/vibrato expression data."""
        self.session.record_phase("express", "running")

        plan_path = Path(self.workdir) / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        base_mid = Path(self.workdir) / "base.mid"

        # C4: Do NOT read binary MIDI as text — just check existence
        if not base_mid.exists():
            self.session.record_phase("express", "done", error="base.mid not found")
            self.session.set_done()
            logger.warning("Session %s: base.mid missing, skipping expression injection", self.session_id)
            return

        # Generate expression plan via orchestrator agent
        message = (
            f"Generate an expression plan (JSON) for the following composition.\n"
            f"Key: {plan.get('key', 'C')}, Scale: {plan.get('scale', 'major')}, "
            f"BPM: {plan.get('bpm', 120)}, Form: {plan.get('form', 'ABA')}.\n\n"
            f"Respond with a JSON object containing:\n"
            f'- "cc7_volume": array of {{beat, value}}\n'
            f'- "cc10_pan": array of {{beat, value}}\n'
            f'- "cc91_reverb": array of {{beat, value}}\n'
            f'- "pitch_bend": array of {{beat, channel, value}}\n'
            f'- "vibrato": array of {{start_beat, end_beat, channel, rate, depth}}\n'
        )

        response = await self._run_agent("clef-orchestrator", message, plan=plan)
        expression_plan = self._extract_json(response)

        # Save expression plan
        expr_plan_path = Path(self.workdir) / "expression_plan.json"
        expr_plan_path.write_text(
            json.dumps(expression_plan, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Inject expression into MIDI
        output_dir = Path(self.workdir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "final.mid"

        from clef_server.tools import inject_expression
        inject_expression(str(base_mid), str(expr_plan_path), str(output_path))

        self.session.record_phase("express", "done")
        self.session.set_done(output_files=[str(output_path.relative_to(Path(self.workdir)))])
        logger.info("Session %s: Phase 4 (express) done, output=%s", self.session_id, output_path)
