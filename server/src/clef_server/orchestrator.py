"""Compose orchestrator -- manages the 6-phase composition workflow.

Phase flow:
  parse (confirm) -> sample (confirm) -> create -> iterate -> review (confirm) -> express -> done
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_framework import Message
from pydantic import BaseModel, Field, model_validator

from clef_server.sessions import PHASES, PHASE_ORDER, SessionManager
from clef_server.tools import ToolMeta, ToolSafety

logger = logging.getLogger(__name__)


# === Custom exceptions ===

class RecoverableAgentError(RuntimeError):
    """Agent failed due to a transient/transiently-recoverable error (500, timeout, etc.)."""
    pass


# --- Plan schema validation ---

class _PlanSection(BaseModel):
    id: str
    name: str
    measures: int = Field(gt=0)


class _PlanOrchestration(BaseModel):
    melody: dict = Field(default_factory=dict)
    harmony: dict = Field(default_factory=dict)
    bass: dict = Field(default_factory=dict)
    drums: dict = Field(default_factory=dict)


class _PlanSchema(BaseModel):
    """Minimal validation for LLM-generated plan.json."""
    title: str = Field(min_length=1)
    key: str = Field(min_length=1)
    scale: str
    bpm: int = Field(gt=30, lt=300)
    time_signature: str
    form: str
    total_bars: int = Field(gt=0, default=32)
    sections: list[_PlanSection] = Field(min_length=1)
    orchestration: _PlanOrchestration
    generation_order: list[str] = Field(default_factory=lambda: ["harmony", "melody"])

    @model_validator(mode="after")
    def sync_total_bars(self) -> "_PlanSchema":
        calculated = sum(s.measures for s in self.sections)
        if calculated > 0:
            self.total_bars = calculated
        return self

# Re-export for convenience
__all__ = ["ComposeOrchestrator", "PHASE_ORDER"]


# Global session manager singleton (shared across routes/orchestrator)
_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    """Return the global SessionManager instance."""
    return _session_manager


# === Concurrency batching ===

@dataclass
class _CallBatch:
    safe: bool
    calls: list[dict]


# === Microcompact ===

_COMPRESSIBLE_TOOLS = frozenset({"validate_abc", "abc_lint"})


# === File cache ===

@dataclass
class _FileCache:
    """Cross-iteration file change detection (MD5 hash)."""
    _hashes: dict[str, str] = field(default_factory=dict)
    _contents: dict[str, str] = field(default_factory=dict)

    def get_if_unchanged(self, path: str) -> str | None:
        """Return cached content if file unchanged, else None (first read or changed)."""
        try:
            current = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        h = hashlib.md5(current.encode()).hexdigest()
        if self._hashes.get(path) == h:
            return self._contents[path]
        self._hashes[path] = h
        self._contents[path] = current
        return None

    def invalidate(self, path: str) -> None:
        self._hashes.pop(path, None)
        self._contents.pop(path, None)


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

    # Maximum retry / iteration counts (defaults, overridden by settings)
    MAX_MELODY_GATE_RETRIES = 3
    MAX_ITERATION_ROUNDS = 3

    # Rate-limit pacing: seconds to sleep between sequential agent calls
    # to avoid 429 (code 1302) from API providers like Zhipu.
    INTER_AGENT_DELAY = 2   # between voice generations (sample/create)
    INTER_ROUND_DELAY = 3   # between best-of-N repair rounds

    # Voice label mapping: role -> ABC voice number
    VOICE_MAP = {"melody": "V:1", "harmony": "V:2", "rhythm": "V:3+V:4"}
    _VOICE_TO_AGENT = {"V:1": "clef-composer", "V:2": "clef-harmonist", "V:3": "clef-rhythmist", "V:4": "clef-rhythmist"}

    # Agent config key -> agent factory name in agents.yaml
    VOICE_AGENT_MAP = {"melody": "clef-composer", "harmony": "clef-harmonist", "rhythm": "clef-rhythmist"}

    # Display names for sub-step progress (Chinese)
    _VOICE_DISPLAY_NAMES = {
        "melody": "生成旋律",
        "harmony": "生成和声",
        "rhythm": "生成节奏",
    }

    def __init__(
        self,
        session_id: str,
        providers: dict[str, Any],
        workdir: str,
        settings: dict[str, Any] | None = None,
        profile_overrides: dict[str, str] | None = None,
    ) -> None:
        self.session_id = session_id
        self.providers = providers
        self.workdir = workdir
        # Resolve project root (where .claude/agents/ lives)
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        # Settings-driven workflow params (shadow class constants)
        self._settings = settings or {}
        self.max_iteration_rounds = self._settings.get("max_iterations", self.MAX_ITERATION_ROUNDS)
        self.max_melody_gate_retries = self.MAX_MELODY_GATE_RETRIES  # not configurable via settings
        self.review_threshold = self._settings.get("review_threshold", 7)
        self.skip_review = self._settings.get("skip_review", False)
        self._validation_failures: list[dict] = []
        self._file_cache = _FileCache()
        self._iteration_history: list[dict] = []

        # Load agent configs from agents.yaml (falls back to hardcoded defaults)
        self._agent_defs = self._load_agent_defs()

        # Apply profile overrides (only model_alias, not temperature/max_tool_calls/etc.)
        if profile_overrides:
            for agent_name, model_alias in profile_overrides.items():
                if agent_name in self._agent_defs:
                    self._agent_defs[agent_name]["model_alias"] = model_alias
                    logger.info("Profile override: %s → %s", agent_name, model_alias)

        # Per-provider rate limiting (token bucket, keyed by model_alias)
        from clef_server.concurrency import ProviderRateLimiter
        self._rate_limiter = ProviderRateLimiter()

    # ------------------------------------------------------------------
    # Concurrency helpers (改进 1)
    # ------------------------------------------------------------------

    def _partition_agent_calls(self, calls: list[dict]) -> list[_CallBatch]:
        """Partition agent calls into safe/unsafe batches."""
        from clef_server.tools import _TOOL_META, ToolSafety

        batches: list[_CallBatch] = []
        for call in calls:
            tools = call.get("tools", [])
            all_safe = all(
                _TOOL_META.get(t, ToolMeta(ToolSafety.EXCLUSIVE_WRITE)).safety != ToolSafety.EXCLUSIVE_WRITE
                for t in tools
            )
            if all_safe and batches and batches[-1].safe:
                batches[-1].calls.append(call)
            else:
                batches.append(_CallBatch(safe=all_safe, calls=[call]))
        return batches

    async def _run_agent_batch_raw(self, coros: list) -> list:
        """Run coroutines concurrently with error isolation (return_exceptions)."""
        if not coros:
            return []
        return list(await asyncio.gather(*coros, return_exceptions=True))

    # ------------------------------------------------------------------
    # Microcompact (改进 2)
    # ------------------------------------------------------------------

    def _microcompact_messages(self, messages: list[dict]) -> list[dict]:
        """Compress compressible tool output to pass/fail summary."""
        compressed = []
        for msg in messages:
            if msg.get("role") == "tool" and msg.get("name") in _COMPRESSIBLE_TOOLS:
                try:
                    result = json.loads(msg.get("content", "{}"))
                    summary = {
                        "tool": msg["name"],
                        "pass": result.get("pass", result.get("is_valid", result.get("report", {}).get("is_valid"))),
                        "issues_count": result.get("count", len(result.get("issues", []))),
                        "has_failures": result.get("has_failures", False),
                    }
                    if result.get("issues"):
                        fails = [i for i in result["issues"] if isinstance(i, dict) and i.get("severity") == "FAIL"]
                        if fails:
                            summary["fail_items"] = [i.get("check", i.get("rule", str(i))) for i in fails]
                    compressed.append({
                        "role": "tool",
                        "content": json.dumps(summary, ensure_ascii=False),
                        "name": msg.get("name"),
                    })
                except (json.JSONDecodeError, KeyError):
                    compressed.append(msg)
            else:
                compressed.append(msg)
        return compressed

    # ------------------------------------------------------------------
    # Agent metadata (改进 4)
    # ------------------------------------------------------------------

    @staticmethod
    def _stamp_agent_meta(content: str, agent: str, voice: str, round_num: int) -> str:
        """Inject % ClefMeta comment at top of ABC content."""
        meta = json.dumps({
            "agent": agent,
            "voice": voice,
            "round": round_num,
            "timestamp": time.time(),
        }, ensure_ascii=False)
        return f"% ClefMeta: {meta}\n{content}"

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

    async def resume(
        self,
        user_feedback: str | None = None,
        action: str = "continue",
        saved_confirmation_data: dict | None = None,
    ) -> None:
        """Resume from a confirmation checkpoint.

        Args:
            user_feedback: Optional text feedback from the user.
            action: "continue" (advance) or "revise" (iterate).
            saved_confirmation_data: Snapshot from before the route cleared it.
        """
        data = saved_confirmation_data
        phase = data.get("phase") if data else None
        if phase is None:
            raise RuntimeError("No saved confirmation data for resume")

        # Explicit "revise" action: always iterate regardless of phase
        if action == "revise":
            if phase == "sample":
                await self._phase_sample(feedback=user_feedback)
            elif phase == "review":
                await self._phase_iterate(extra_feedback=user_feedback)
            else:
                await self._phase_sample(feedback=None)
            return

        # action == "continue"
        if phase == "parse":
            await self._phase_sample(feedback=None)
            return

        if phase == "sample":
            await self._advance_phase("sample")
            return

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
        # Graceful cancel: check at phase boundary
        if self.session.cancel_requested:
            self.session.set_cancelled()
            logger.info("Session %s cancelled after phase %s", self.session_id, from_phase)
            return

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
    # MIDI program injection
    # ------------------------------------------------------------------

    def _inject_midi_programs(self, score_path: Path, plan: dict) -> None:
        """Inject %%MIDI program directives into score.abc based on plan.json.

        Maps each voice (V:1..V:4) to its orchestration part and injects
        the midi_program number. Skips voices that already have a program directive.
        """
        orch = plan.get("orchestration", {})
        voice_map = {
            1: orch.get("melody", {}),
            2: orch.get("harmony", {}),
            3: orch.get("bass", {}),
            4: orch.get("drums", {}),
        }

        text = score_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        new_lines: list[str] = []
        injected_voices: set[int] = set()

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("%%MIDI program"):
                continue
            new_lines.append(line)
            for voice_num, part in voice_map.items():
                if stripped == f"V:{voice_num}" and voice_num not in injected_voices:
                    prog = part.get("midi_program")
                    if prog is not None:
                        new_lines.append(f"%%MIDI program {prog}")
                        injected_voices.add(voice_num)

        score_path.write_text("\n".join(new_lines), encoding="utf-8")

    # ------------------------------------------------------------------
    # Output collection
    # ------------------------------------------------------------------

    def _collect_outputs(self) -> list[str]:
        """Collect output file paths from workdir root (.mid, .abc, .json)."""
        workdir = Path(self.workdir)
        return [
            p.relative_to(workdir).as_posix()
            for p in sorted(workdir.glob("*"))
            if p.is_file() and p.suffix in (".mid", ".abc", ".json")
        ]

    # ------------------------------------------------------------------
    # Plan summary builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_plan_summary(plan: dict) -> dict:
        """Build a rich parameter summary from plan.json for the confirmation UI."""
        total_bars = plan.get("total_bars", 0)
        bpm = plan.get("bpm", 0)
        ts = plan.get("time_signature", "4/4")
        beats_per_bar = int(ts.split("/")[0]) if "/" in ts else 4

        # Duration
        duration_sec = (total_bars * beats_per_bar / bpm * 60) if bpm > 0 else 0
        if duration_sec >= 60:
            duration_str = f"~{int(duration_sec // 60)}分{int(duration_sec % 60)}秒"
        else:
            duration_str = f"~{duration_sec:.0f}秒"

        # Section structure compact form: "ABA（4+7+4 小节）"
        sections = plan.get("sections", [])
        bar_counts = [str(s.get("measures", "?")) for s in sections]
        section_structure = f"{plan.get('form', '')}（{'+'.join(bar_counts)} 小节）"

        # Orchestration description
        orch = plan.get("orchestration", {})
        voice_cn = {"melody": "旋律", "harmony": "和声", "bass": "低音", "drums": "鼓"}
        inst_parts = []
        for role in ["melody", "harmony", "bass", "drums"]:
            part = orch.get(role, {})
            if part:
                name = part.get("name", part.get("instrument", ""))
                inst_parts.append(f"{name}{voice_cn.get(role, role)}")

        # SF2 status
        sf2_count = sum(
            1
            for role in ["melody", "harmony", "bass"]
            if isinstance(orch.get(role), dict) and "sf2" in orch[role]
        )
        sf2_status = f"已加载 {sf2_count} 个声部音色" if sf2_count > 0 else "未配置"

        # Demo length with duration
        demo_bars = plan.get("demo_length_bars", 0)
        demo_sec = (demo_bars * beats_per_bar / bpm * 60) if bpm > 0 and demo_bars > 0 else 0
        demo_str = f"{demo_bars} 小节（~{demo_sec:.0f}秒）" if demo_sec > 0 else f"{demo_bars} 小节"

        return {
            "duration": duration_str,
            "section_structure": section_structure,
            "orchestration_desc": " + ".join(inst_parts),
            "sf2_status": sf2_status,
            "demo_length": demo_str,
        }

    # ------------------------------------------------------------------
    # Phase 0: Parse + Plan
    # ------------------------------------------------------------------

    async def _phase_parse(self, prompt: str) -> None:
        """Phase 0: Parse requirements and generate plan.json via LLM."""
        client = next(iter(self.providers.values()), None)
        if not client:
            raise RuntimeError("No LLM provider available")

        self.session.record_phase("parse", "running")
        self.session.record_sub_step("解析用户需求", "running")

        system_prompt = (
            "You are a music composition planner. Given a user's music description, "
            "generate a structured plan.json with these fields:\n"
            "- title: string\n"
            "- key: string (e.g. 'C', 'D', 'Bb')\n"
            "- scale: 'major' or 'minor'\n"
            "- bpm: integer\n"
            "- time_signature: string (e.g. '4/4')\n"
            "- form: string (e.g. 'ABA', 'AB', 'AABA')\n"
            "- total_bars: integer (total number of bars, MUST equal sum of all sections' measures)\n"
            "- sections: array of {id, name, measures (REQUIRED integer), start_beat, energy_level, dynamics, balance_intent, melody_strategy}. "
            "Each section MUST have a 'measures' field specifying the number of bars.\n"
            "- orchestration: object with melody/harmony/bass/drums sub-objects, "
            "each having name, channel, instrument, range, register, midi_program (GM program number 0-127)\n"
            "- generation_order: array like ['harmony', 'melody']\n\n"
            "VALIDATION: Verify that sum(sections[].measures) == total_bars. If not, adjust.\n\n"
            "Respond ONLY with valid JSON. No markdown, no explanation."
        )

        messages = [
            Message(role="system", contents=[system_prompt]),
            Message(role="user", contents=[prompt]),
        ]

        response = await client.get_response(messages)
        self.session.record_sub_step("解析用户需求", "done")
        self.session.record_sub_step("生成 plan.json", "running")
        content = str(response.messages[0].contents[0]) if response.messages else ""
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rstrip("`")

        try:
            plan = json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"LLM returned invalid plan JSON: {e}") from e

        # Normalize LLM output: coerce types that models often get wrong
        for section in plan.get("sections", []):
            if "id" in section:
                section["id"] = str(section["id"])
            if "name" in section:
                section["name"] = str(section["name"])

        # Validate plan against schema
        try:
            validated = _PlanSchema.model_validate(plan)
            plan = validated.model_dump()
            self.session.record_sub_step("验证规划参数", "done")
        except Exception as e:
            raise RuntimeError(f"LLM plan failed schema validation: {e}") from e

        # Override total_bars from user-specified duration if present
        plan = self._apply_duration_constraint(plan, prompt)

        # Calculate demo_length_bars proportionally (not LLM-generated)
        plan["demo_length_bars"] = self._calculate_demo_bars(plan["total_bars"])

        # Inject SF2 profile data into orchestration if SF2 is configured
        plan = self._inject_sf2_data(plan)

        # Persist plan.json to workdir
        plan_path = Path(self.workdir) / "plan.json"
        plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.session.record_sub_step("生成 plan.json", "done")
        self.session.record_sub_step("验证规划参数", "running")

        # Rename workdir to use title instead of prompt snippet
        title = plan.get("title", "")
        if title:
            from clef_server.config import rename_workdir_with_title
            new_workdir = rename_workdir_with_title(self.workdir, title)
            self.workdir = new_workdir
            self.session.workdir = new_workdir

        self.session.record_phase("parse", "done")
        summary = self._build_plan_summary(plan)
        self.session.set_awaiting_confirm(confirmation_data={
            "phase": "parse",
            "title": "确认音乐规划",
            "plan": plan,
            "summary": summary,
            "user_prompt": self.session.user_prompt,
        })
        logger.info("Session %s: Phase 0 done, plan saved", self.session_id)

    # ------------------------------------------------------------------
    # Agent execution helpers
    # ------------------------------------------------------------------

    # Agent definitions: prompt file, model alias, skills
    # (fallback defaults — overridden by config/agents.yaml when available)
    _AGENT_DEFS: dict[str, dict[str, Any]] = {
        "clef-composer": {
            "prompt_md": "clef-composer.md",
            "model_alias": "deepseek",
            "skills": ["melody", "orchestration", "abc"],
            "max_tool_calls": 10,
        },
        "clef-harmonist": {
            "prompt_md": "clef-harmonist.md",
            "model_alias": "deepseek",
            "skills": ["harmony", "abc"],
            "max_tool_calls": 10,
        },
        "clef-rhythmist": {
            "prompt_md": "clef-rhythmist.md",
            "model_alias": "deepseek",
            "skills": ["rhythm", "abc"],
            "max_tool_calls": 10,
        },
        "clef-reviewer": {
            "prompt_md": "clef-reviewer.md",
            "model_alias": "deepseek",
            "skills": ["structure", "orchestration", "abc"],
            "max_tool_calls": 10,
        },
        "clef-orchestrator": {
            "prompt_md": "clef-orchestrator.md",
            "model_alias": "deepseek",
            "skills": ["orchestration", "abc"],
            "max_tool_calls": 10,
        },
        "clef-repair": {
            "prompt_md": "server/config/prompts/clef-repair.md",
            "model_alias": "anthropic-haiku",
            "skills": ["abc"],
            "temperature": 0.2,
            "max_tool_calls": 6,
        },
    }

    def _load_agent_defs(self) -> dict[str, dict[str, Any]]:
        """Load agent configs from config/agents.yaml, falling back to hardcoded defaults."""
        try:
            from clef_server.config import load_agent_configs
            config_path = self.project_root / "server" / "config" / "agents.yaml"
            configs = load_agent_configs(config_path, base_dir=self.project_root)
            defs: dict[str, dict[str, Any]] = {}
            for name, cfg in configs.items():
                defs[name] = {
                    "prompt_md": str(cfg.prompt_md),  # full resolved path from agents.yaml
                    "model_alias": cfg.model_alias,
                    "skills": cfg.skills,
                    "temperature": cfg.temperature,
                    "max_tool_calls": cfg.max_tool_calls,
                }
            logger.info("Loaded agent configs from agents.yaml: %s", list(defs.keys()))
            return defs
        except Exception as exc:
            logger.warning("Failed to load agents.yaml, using defaults: %s", exc)
            return dict(self._AGENT_DEFS)

    async def _run_agent(
        self,
        agent_name: str,
        message: str,
        plan: dict | None = None,
        score_abc: str | None = None,
    ) -> str:
        """Run an agent with agentic tool-use loop.

        Builds a 3-layer prompt (instructions / skills / context),
        provides tool schemas, and runs a ReAct loop until the LLM
        stops calling tools or max_tool_calls is reached.
        """
        agent_def = self._agent_defs.get(agent_name)
        if not agent_def:
            logger.warning("Unknown agent %s, returning placeholder", agent_name)
            return f"[placeholder ABC for {agent_name}]"

        try:
            from clef_server.agent_loop import run_agent_loop
            from clef_server.agents import build_instructions
            from clef_server.middleware import ClefContextMiddleware
            from clef_server.tools import _AGENT_TOOL_MAP, TOOLS_REGISTRY, get_tool_schemas

            # Build 3-layer instructions
            prompt_md = agent_def["prompt_md"]
            prompt_path = Path(prompt_md)
            if not prompt_path.is_absolute():
                prompt_path = self.project_root / prompt_md
            if not prompt_path.exists():
                logger.warning("Agent prompt not found: %s", prompt_path)
                return f"[placeholder ABC for {agent_name}]"

            skills_dir = self.project_root / ".claude" / "skills" / "clef-compose"
            middleware = ClefContextMiddleware(
                skills=agent_def["skills"],
                skills_dir=skills_dir,
            )
            instructions = build_instructions(
                prompt_md=prompt_path,
                middleware=middleware,
                plan=plan,
                score_abc=score_abc,
                workdir=self.workdir,
            )

            # Resolve LLM client with explicit fallback logging
            model_alias = agent_def["model_alias"]
            client = self.providers.get(model_alias)
            if client is None:
                available = list(self.providers.keys())
                logger.warning(
                    "Agent %s: model_alias '%s' not found in providers %s, "
                    "falling back to first available",
                    agent_name, model_alias, available,
                )
                client = next(iter(self.providers.values()), None)
            if not client:
                raise RuntimeError(f"No LLM client available for {agent_name} (alias={model_alias})")

            # Build tool schemas and executor
            tool_schemas = get_tool_schemas(agent_name)
            tool_executor = self._make_tool_executor(agent_name)

            # Build system + user messages using 3-layer structure
            system_prompt = instructions.build_system_message()
            user_message = instructions.build_user_message(message)

            max_tool_calls = agent_def.get("max_tool_calls", agent_def.get("max_turns", 10))
            temperature = agent_def.get("temperature", 0.7)

            logger.info(
                "Agent %s: starting loop (max_tool_calls=%d, tools=%s, model=%s)",
                agent_name, max_tool_calls, [s["function"]["name"] for s in tool_schemas], model_alias,
            )

            # Acquire rate limiter token before API calls (uses model_alias as key)
            async with self._rate_limiter.acquire(model_alias):
                result = await run_agent_loop(
                    client=client,
                    system_prompt=system_prompt,
                    user_message=user_message,
                    tools=tool_schemas,
                    tool_executor=tool_executor,
                    temperature=temperature,
                    max_tool_calls=max_tool_calls,
                )

            logger.info(
                "Agent %s: loop completed (tool_calls_used=%d, tool_calls=%d)",
                agent_name, result.tool_calls_used, result.tool_calls_count,
            )

            return result.text

        except Exception as exc:
            logger.error("Agent %s execution failed: %s", agent_name, exc)
            # Classify as recoverable if the error is a transient API failure
            exc_str = str(exc).lower()
            is_recoverable = any(
                kw in exc_str
                for kw in ("500", "502", "503", "504", "timeout", "timed out", "connection")
            )
            if is_recoverable:
                raise RecoverableAgentError(
                    f"Agent {agent_name} failed (recoverable): {exc}"
                ) from exc
            raise RuntimeError(f"Agent {agent_name} failed: {exc}") from exc

    def _make_tool_executor(self, agent_name: str):
        """Create a tool executor closure for the given agent.

        The executor resolves tool calls by name from TOOLS_REGISTRY,
        injecting ``workdir`` automatically for path-based tools.
        Includes deduplication cache for read-only validation tools.
        """
        from clef_server.tools import TOOLS_REGISTRY, _AGENT_TOOL_MAP

        agent_tool_names = set(_AGENT_TOOL_MAP.get(agent_name, []))
        workdir = self.workdir

        # Deduplication cache for read-only tools (cleared per agent loop)
        _DEDUP_TOOLS = frozenset({"abc_lint", "validate_abc", "validate_rhythm_skeleton", "read_file", "list_files"})
        _call_cache: dict[str, Any] = {}

        def executor(call: dict) -> dict:
            tool_name = call.get("name", "")
            raw_args = call.get("arguments", {})

            # Normalize arguments: may be JSON string or dict
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    return {"error": f"Invalid JSON arguments for {tool_name}: {raw_args[:200]}"}
            else:
                args = raw_args

            if tool_name not in agent_tool_names:
                return {"error": f"Tool '{tool_name}' not allowed for agent '{agent_name}'"}

            # Deduplication: return cached result for identical read-only tool calls
            if tool_name in _DEDUP_TOOLS:
                # Normalize args for cache key: strip strings, resolve paths to
                # absolute to avoid cache misses from plan_path variations
                norm_args = {}
                for k, v in args.items():
                    if isinstance(v, str):
                        v = v.strip()
                        # Resolve path-like args (plan_path, file_path) to absolute
                        if k.endswith("path") and workdir and not v.startswith("/") and not v[1:2] == ":":
                            v = str((Path(workdir) / v).resolve())
                    norm_args[k] = v
                cache_key = json.dumps({"tool": tool_name, "args": norm_args}, sort_keys=True)
                if cache_key in _call_cache:
                    logger.info("[DEDUP] %s — returning cached result (annotated)", tool_name)
                    cached = _call_cache[cache_key]
                    if isinstance(cached, dict):
                        return {**cached, "_dedup": True, "_dedup_note": "You already called this tool with identical arguments. Use the previous result instead of calling again."}
                    return cached

            func = TOOLS_REGISTRY.get(tool_name)
            if func is None:
                return {"error": f"Tool '{tool_name}' not found in registry"}

            # Unwrap FunctionTool to get the underlying Python function
            raw_func = getattr(func, "func", func)

            # Enforce workdir for path-based tools that accept it (agent cannot override)
            if tool_name in ("read_file", "write_file", "list_files"):
                args = {**args, "workdir": workdir}

            # Security: limit write_file content size (256KB max)
            if tool_name == "write_file" and len(args.get("content", "")) > 262144:
                return {"error": f"write_file content exceeds 256KB limit ({len(args.get('content', ''))} bytes)"}

            try:
                result = raw_func(**args)
                # Cache result for dedup-eligible tools
                if tool_name in _DEDUP_TOOLS:
                    _call_cache[cache_key] = result
                return result
            except Exception as e:
                return {"error": str(e)}

        return executor

    @staticmethod
    def _looks_like_abc(text: str) -> bool:
        """Heuristic: does the text look like valid ABC notation?"""
        stripped = text.strip()
        if not stripped:
            return False
        # Must start with a standard ABC header or voice label
        has_abc_header = any(stripped.startswith(h) for h in ("X:", "T:", "M:", "K:", "L:", "V:"))
        # Must contain at least one bar line (|) or note letters
        has_music = "|" in stripped or any(c in stripped for c in "abcdefgABCDEFG")
        return has_abc_header and has_music

    def _extract_abc(self, text: str) -> str:
        """Extract ABC notation from agent response text.

        Handles markdown code fences (```abc ... ```) or raw ABC content.
        Rejects text that clearly isn't ABC (tool-call syntax, prose, etc.).
        """
        text = text.strip()
        # Guard against raw Content objects leaking into text
        if "Content(type=" in text:
            logger.warning("_extract_abc: received raw Content object, returning empty")
            return ""
        # Reject text containing tool-call artifacts (DSML, XML tool tags, etc.)
        tool_markers = ("<|DSML|>", "<function_calls>", "</invoke>", "tool_call", "FunctionCall")
        if any(m in text for m in tool_markers):
            logger.warning("_extract_abc: response contains tool-call syntax, returning empty")
            return ""
        # Try fenced block first
        fence_match = re.search(r"```(?:abc)?\s*\n(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
        # Raw text must look like ABC
        elif not self._looks_like_abc(text):
            logger.warning("_extract_abc: text does not look like ABC (first 80 chars: %s...), returning empty",
                           text[:80])
            return ""

        # Trim trailing rest-only bars
        text = self._trim_trailing_rests(text)
        return text

    @staticmethod
    def _is_placeholder(text: str) -> bool:
        """Check if extracted ABC is a placeholder (not real music)."""
        lower = text.lower().strip()
        return (
            "placeholder" in lower
            or len(lower) < 10
            or not any(c in lower for c in "|abcdefg'")
        )

    def _quick_lint_check(self, abc_text: str, plan_path: Path) -> str | bool:
        """Run abc_lint on extracted ABC. Returns True if clean, or error string for feedback."""
        from clef_server.tools import abc_lint
        result = abc_lint(abc_text, str(plan_path))
        if "error" in result:
            return True  # Lint itself failed — don't block, accept as-is
        if result.get("pass", True):
            return True
        issues = result.get("issues", [])
        if not issues:
            return True
        lines = [f"ABC 格式检查发现 {len(issues)} 个问题："]
        for issue in issues[:5]:
            lines.append(f"- {issue}")
        if len(issues) > 5:
            lines.append(f"- ...还有 {len(issues) - 5} 个问题")
        return "\n".join(lines)

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from agent response, handling markdown fencing."""
        text = text.strip()
        # Reject text containing tool-call artifacts
        tool_markers = ("<|DSML|>", "<function_calls>", "</invoke>", "tool_call", "FunctionCall")
        if any(m in text for m in tool_markers):
            logger.warning("_extract_json: response contains tool-call syntax, returning pass verdict")
            return {"verdict": "pass"}
        fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("_extract_json: failed to parse JSON, returning pass verdict")
            return {"verdict": "pass"}

    # ------------------------------------------------------------------
    # Prompt builders & helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_duration_constraint(plan: dict, user_prompt: str) -> dict:
        """If the user prompt specifies a duration, override total_bars and redistribute sections.

        Supports patterns like "45秒", "30秒左右", "1分钟", "1分30秒", "90s".
        """
        # Extract duration in seconds from prompt
        seconds = 0.0
        # Match "X分Y秒" or "X分钟Y秒"
        m = re.search(r"(\d+)\s*(?:分|分钟)\s*(?:(\d+)\s*秒)?", user_prompt)
        if m:
            seconds = int(m.group(1)) * 60
            if m.group(2):
                seconds += int(m.group(2))
        else:
            # Match "X秒" or "Xs"
            m = re.search(r"(\d+)\s*(?:秒|s)", user_prompt)
            if m:
                seconds = float(m.group(1))

        if seconds <= 0:
            return plan

        bpm = plan.get("bpm", 120)
        ts = plan.get("time_signature", "4/4")
        beats_per_bar = float(ts.split("/")[0]) if "/" in ts else 4.0
        target_bars = round(seconds * bpm / 60.0 / beats_per_bar)
        target_bars = max(8, target_bars)  # minimum 8 bars

        if target_bars == plan.get("total_bars"):
            return plan

        logger.info(
            "Duration constraint: user wants ~%.0fs, adjusting total_bars %d → %d (bpm=%d, %s)",
            seconds, plan.get("total_bars"), target_bars, bpm, ts,
        )

        # Redistribute sections proportionally
        sections = plan.get("sections", [])
        if not sections:
            return plan

        old_total = sum(s.get("measures", 1) for s in sections)
        remaining = target_bars
        for i, sec in enumerate(sections):
            if i == len(sections) - 1:
                sec["measures"] = max(2, remaining)
            else:
                ratio = sec.get("measures", 1) / max(old_total, 1)
                new_measures = max(2, round(ratio * target_bars))
                sec["measures"] = new_measures
                remaining -= new_measures

        plan["total_bars"] = target_bars
        return plan

    @staticmethod
    def _trim_trailing_rests(abc_text: str) -> str:
        """Remove trailing rest-only bars from ABC voice content.

        Detects lines consisting solely of rests (z2, z4, z8, etc.) and bars (|)
        at the end of the text and strips them.
        """
        lines = abc_text.rstrip().split("\n")
        # Work backwards, find last non-rest line index (immutable)
        last_non_rest = len(lines)
        while last_non_rest > 0:
            stripped = lines[last_non_rest - 1].strip()
            if re.match(r'^[\s|z\d/]*$', stripped) and 'z' in stripped:
                last_non_rest -= 1
            else:
                break
        return "\n".join(lines[:last_non_rest])

    @staticmethod
    def _calculate_demo_bars(total_bars: int) -> int:
        """Calculate demo_length_bars as ~30% of total_bars, clamped to [8, 64]."""
        if total_bars <= 0:
            return 8
        return max(8, min(64, round(total_bars * 0.3)))

    @staticmethod
    def _parse_voice_blocks(score_text: str) -> dict[str, str]:
        """Extract voice blocks from a merged score.abc.

        Returns {"V:1": "C D E F|...", "V:2": "[FAc] ...", ...}
        """
        blocks: dict[str, str] = {}
        lines = score_text.split("\n")
        current_voice: str | None = None
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            voice_match = re.match(r'^(V:\d[\+\d]*)', stripped)
            if voice_match:
                if current_voice and current_lines:
                    blocks[current_voice] = "\n".join(current_lines).strip()
                current_voice = voice_match.group(1)
                current_lines = []
            elif current_voice:
                current_lines.append(line)

        if current_voice and current_lines:
            blocks[current_voice] = "\n".join(current_lines).strip()

        return blocks

    _BAR_RE = re.compile(r'(?<![\|:])\|(?![\|:])')

    @staticmethod
    def _count_bars(abc_text: str) -> int:
        """Count bar lines (|) in ABC text, excluding ||, |:, and :|."""
        count = 0
        for line in abc_text.strip().split("\n"):
            stripped = line.strip()
            if stripped.startswith("%"):
                continue
            count += len(ComposeOrchestrator._BAR_RE.findall(stripped))
        return count

    @staticmethod
    def _truncate_to_bars(abc_text: str, target_bars: int) -> str:
        """Truncate ABC voice content to exactly target_bars measures."""
        bars_found = 0
        result_parts: list[str] = []
        for line in abc_text.strip().split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("%"):
                result_parts.append(line)
                continue
            bar_positions = [m.start() for m in ComposeOrchestrator._BAR_RE.finditer(line)]
            if not bar_positions:
                result_parts.append(line)
                continue
            new_bars = bars_found + len(bar_positions)
            if new_bars <= target_bars:
                result_parts.append(line)
                bars_found = new_bars
            else:
                remaining = target_bars - bars_found
                if remaining > 0 and bar_positions:
                    end_pos = bar_positions[remaining - 1] + 1
                    result_parts.append(line[:end_pos])
                    bars_found = target_bars
                break
        return "\n".join(result_parts)

    def _store_fragment(
        self,
        fragments: dict[str, str],
        abc_parts: list[str],
        voice_label: str,
        abc_text: str,
        round_num: int = 0,
    ) -> None:
        """Store ABC text into fragments, splitting multi-voice rhythm output (V:3+V:4)."""
        # Stamp agent metadata
        agent = self._VOICE_TO_AGENT.get(voice_label, "unknown")
        abc_text = self._stamp_agent_meta(abc_text, agent, voice_label, round_num)

        if "+" in voice_label:
            rhythm_blocks = self._parse_voice_blocks(abc_text)
            if rhythm_blocks:
                for sub_label in rhythm_blocks:
                    fragments[sub_label] = rhythm_blocks[sub_label]
                if abc_parts is not None:
                    abc_parts.extend(f"{label}\n{content}" for label, content in rhythm_blocks.items())
                return
            logger.warning("Rhythmist output had no V:3/V:4 labels, storing as %s", voice_label)
        fragments[voice_label] = abc_text
        if abc_parts is not None:
            abc_parts.append(f"{voice_label}\n{abc_text}")

    def _inject_sf2_data(self, plan: dict) -> dict:
        """Inject SF2 profile data into plan's orchestration voices.

        Loads the SF2 profile, matches each voice's midi_program to the profile,
        and overrides range/register with real SF2 data.

        Returns a new plan dict with SF2 data injected (does not mutate input).
        """
        sf2_path = self._settings.get("sf2_path", "")
        if not sf2_path:
            return plan

        from clef_server.sf2_profile import load_sf2_profile, midi_to_note

        profile = load_sf2_profile(sf2_path)
        if not profile:
            return plan

        presets = profile.get("presets", {})
        orch = plan.get("orchestration", {})
        new_orch = {}
        for role in ["melody", "harmony", "bass"]:
            part = dict(orch.get(role, {}))
            gm_program = part.get("midi_program")
            if isinstance(gm_program, int) and str(gm_program) in presets:
                preset_data = presets[str(gm_program)]
                part["sf2"] = preset_data
                # Override range/register with real SF2 data
                kr = preset_data.get("key_range", [0, 127])
                part["range"] = f"{midi_to_note(kr[0])}-{midi_to_note(kr[1])}"
                ss = preset_data.get("sweet_spot", [kr[0], kr[1]])
                part["register"] = f"{midi_to_note(ss[0])}-{midi_to_note(ss[1])}"
            new_orch[role] = part

        new_plan = {**plan, "orchestration": new_orch}

        logger.info(
            "Session %s: SF2 profile injected (%s, %d presets)",
            self.session_id, profile.get("sf2_name", "?"),
            profile.get("preset_count", 0),
        )
        return new_plan

    def _build_create_message(self, voice: str, plan: dict) -> str:
        """Build a detailed prompt for the create phase, including section structure."""
        from clef_server.sf2_profile import midi_to_note

        voice_label = self.VOICE_MAP.get(voice, f"V:{voice}")
        total_bars = plan.get("total_bars", 0)
        sections = plan.get("sections", [])
        orch = plan.get("orchestration", {})
        ts = plan.get("time_signature", "4/4")

        # Build section summary
        section_lines = []
        for sec in sections:
            section_lines.append(
                f"  - {sec.get('name', sec.get('id', '?'))}: "
                f"{sec.get('measures', '?')} bars, "
                f"energy={sec.get('energy_level', 'mid')}, "
                f"melody_strategy={sec.get('melody_strategy', 'new')}"
            )
        sections_text = "\n".join(section_lines)

        # Get voice-specific orchestration info
        role_map = {"melody": "melody", "harmony": "harmony", "rhythm": "bass"}
        role = role_map.get(voice, voice)
        voice_orch = orch.get(role, {})
        voice_info = (
            f"  Instrument: {voice_orch.get('instrument', 'N/A')}, "
            f"Range: {voice_orch.get('range', 'N/A')}, "
            f"Register: {voice_orch.get('register', 'N/A')}"
        )

        # SF2 constraints if available
        sf2_section = ""
        sf2 = voice_orch.get("sf2")
        if sf2:
            kr = sf2.get("key_range", [])
            ss = sf2.get("sweet_spot", [])
            chars = sf2.get("characteristics", [])
            char_text = ", ".join(chars) if chars else "N/A"
            sf2_section = (
                f"\n\n## SF2 Instrument Constraints\n"
                f"- Key range: [{kr[0]}, {kr[1]}] ({midi_to_note(kr[0])}-{midi_to_note(kr[1])})\n"
                f"- Sweet spot (recommended register): [{ss[0]}, {ss[1]}] ({midi_to_note(ss[0])}-{midi_to_note(ss[1])})\n"
                f"- Velocity layers: {sf2.get('vel_layers', 'N/A')}\n"
                f"- Characteristics: {char_text}\n"
                f"CRITICAL: Do NOT write notes outside the key range [{kr[0]}, {kr[1]}]!\n"
            )

        # Duration reference (shared by all voices)
        beats_per_measure = int(ts.split("/")[0])
        duration_ref = (
            f"\n\n## Duration Self-Check (MANDATORY)\n"
            f"Time signature: {ts} → {beats_per_measure} beats per measure.\n"
            f"With L:1/8, each measure = {beats_per_measure * 2} eighth-note units.\n"
            f"Duration reference (L:1/8):\n"
            f"  f = 1 unit (eighth note)\n"
            f"  f2 = 2 units (quarter note)\n"
            f"  f4 = 4 units (half note)\n"
            f"  f/2 = 0.5 units (sixteenth note)  ⚠ NOT 1 unit!\n"
            f"  [Ace]2 = 2 units,  z = 1 unit,  z2 = 2 units\n"
            f"VERIFY: sum of durations in EACH measure must = {beats_per_measure * 2}.\n"
            f"Before output, re-check every measure. Do NOT output if any measure is incomplete.\n"
        )

        # Voice-specific rhythm guidance
        voice_rules = ""
        if role == "melody":
            voice_rules = (
                "\n\n## Melody Rules\n"
                "- Follow plan.json melody_strategy per section (new/variation/sequence/development/recap/climax)\n"
                "- Rhythm variety: sections must have contrasting density (sparse vs dense)\n"
                "- Dynamics: at least 2 dynamic levels per section (!mf! base + !ff! climax)\n"
                "- Large intervals (>5 semitones): insert passing notes immediately\n"
            )
        elif role == "harmony":
            voice_rules = (
                "\n\n## Harmony Rules\n"
                "- EVERY measure must be COMPLETELY filled — sum of durations = "
                f"{beats_per_measure * 2} eighth-note units\n"
                "- Chord marks (\"D\") and chord notes ([FAc]) must appear in the SAME measure\n"
                "- Voice leading: common tones keep, non-common tones move by step (≤2 semitones)\n"
                "- Do NOT use the same rhythm pattern in every measure — vary rhythm between sections\n"
                "- Harmony notes must align with melody's strong beats\n"
            )
        elif role == "bass":
            voice_rules = (
                "\n\n## Bass & Drum Rules\n"
                "- Bass: prefer chord root or fifth, reference V:2 chord marks\n"
                "- Drums: adjust density by section energy (sparse in A, fills in B/C transitions)\n"
                "- Drum fills only at section transitions (last 1-2 bars), NOT at piece endings\n"
                "- Bass notes stay within register range from plan.json\n"
            )

        message = (
            f"Generate the full {voice} part as ABC notation.\n"
            f"Use voice label {voice_label}.\n\n"
            f"## Composition Structure\n"
            f"- Key: {plan.get('key', 'C')}\n"
            f"- Scale: {plan.get('scale', 'major')}\n"
            f"- Time: {ts}\n"
            f"- BPM: {plan.get('bpm', 120)}\n"
            f"- Form: {plan.get('form', 'ABA')}\n"
            f"- Total bars: {total_bars}\n\n"
            f"## Sections (must generate content for ALL sections)\n"
            f"{sections_text}\n\n"
            f"## Your Voice Configuration\n"
            f"{voice_info}"
            f"{voice_rules}"
            f"{duration_ref}"
            f"{sf2_section}"
            f"\nOutput only ABC notation for voice {voice_label}. "
            f"CRITICAL: Your output must contain EXACTLY {total_bars} bar lines (|). "
            f"Count your bars before outputting. If you have more than {total_bars} bars, "
            f"remove the excess. If fewer, add rest measures (z)."
        )
        return message

    # ------------------------------------------------------------------
    # Reviewer helper
    # ------------------------------------------------------------------

    async def _call_reviewer(
        self,
        plan: dict,
        melody_only: bool = False,
        is_sample: bool = False,
        extra_context: str = "",
    ) -> dict:
        """Run the reviewer agent and return a review dict.

        Returns {"verdict": "pass"|"revise", ...} or a fallback dict on parse failure.
        """
        score_path = Path(self.workdir) / "score.abc"
        score_text = score_path.read_text(encoding="utf-8") if score_path.exists() else ""

        scope = "melody only" if melody_only else "full composition"
        if is_sample:
            scope = "direction sample (incomplete, for style/character evaluation only)"

        message = (
            f"Review the following ABC score ({scope}):\n\n"
            f"Score:\n```\n{score_text}\n```\n\n"
            f"Plan:\n```json\n{json.dumps(plan, indent=2)}\n```\n\n"
        )

        if is_sample:
            message += (
                "IMPORTANT: This is a DIRECTION SAMPLE, not a complete composition. "
                "Evaluate based on:\n"
                "- Melody quality and character (contour, phrasing, motif)\n"
                "- Harmonic direction and chord progression logic\n"
                "- Rhythmic character and groove\n"
                "- Style consistency with the plan\n\n"
                "DO NOT penalize for:\n"
                "- Incomplete structure (only a few bars of each section)\n"
                "- Missing section development or recapitulation\n"
                "- Short overall length\n\n"
            )

        message += (
            "You MUST respond with a JSON object in this exact format (no markdown, no extra text):\n"
            "```json\n"
            "{\n"
            '  "dimensions": {\n'
            '    "melody": {"score": 7, "issues": [{"bar": "1-4", "severity": "WARN", "description": "...", "suggestion": "..."}]},\n'
            '    "harmony": {"score": 8, "issues": []},\n'
            '    "rhythm": {"score": 7, "issues": []},\n'
            '    "structure": {"score": 8, "issues": []},\n'
            '    "style": {"score": 7, "issues": []},\n'
            '    "orchestration": {"score": 8, "issues": []}\n'
            "  },\n"
            '  "overall_score": 7.5,\n'
            '  "verdict": "pass",\n'
            '  "summary": "Brief overall assessment."\n'
            "}\n"
            "```\n"
            "IMPORTANT: Every dimension MUST have a score (0-10). If you find issues, include them "
            "in the issues array with bar, severity (WARN/FAIL), description, and suggestion.\n"
        )
        if extra_context:
            message += f"\nAdditional context: {extra_context}\n"

        response_text = await self._run_agent("clef-reviewer", message, plan=plan, score_abc=score_text)
        raw = self._extract_json(response_text)
        return self._normalize_review(raw)

    def _normalize_review(self, raw: dict) -> dict:
        """Normalize reviewer output into a flat structure for the frontend.

        The reviewer agent outputs nested "dimensions": {"melody": {"score": 7, ...}, ...}.
        The frontend expects flat "scores": {"melody": 7, ...} + "verdict" + "summary".
        """
        result: dict = {"verdict": raw.get("verdict", "pass"), "scores": {}}

        # Extract from nested "dimensions" format (reviewer's standard output)
        dimensions = raw.get("dimensions", {})
        if isinstance(dimensions, dict):
            for key, val in dimensions.items():
                if isinstance(val, dict):
                    result["scores"][key] = val.get("score", 0)
                elif isinstance(val, (int, float)):
                    result["scores"][key] = val

        # Fallback: if agent returned flat "scores" directly
        if not result["scores"] and "scores" in raw:
            result["scores"] = raw["scores"]

        # Collect all issues into a flat list
        all_issues: list[str] = []
        if isinstance(dimensions, dict):
            for val in dimensions.values():
                if isinstance(val, dict) and "issues" in val:
                    for issue in val["issues"]:
                        if isinstance(issue, dict):
                            all_issues.append(issue.get("description", str(issue)))
                        else:
                            all_issues.append(str(issue))
        if not all_issues and "issues" in raw:
            all_issues = raw["issues"]
        result["issues"] = all_issues

        # Summary: prefer explicit field, otherwise derive from overall_score
        if "summary" in raw:
            result["summary"] = raw["summary"]
        elif "overall_score" in raw:
            result["summary"] = f"Overall: {raw['overall_score']}/10"
        else:
            avg = sum(result["scores"].values()) / max(len(result["scores"]), 1)
            result["summary"] = f"Overall: {avg:.1f}/10"

        raw_overall = raw.get("overall_score")
        if raw_overall is not None:
            result["overall_score"] = raw_overall
        else:
            result["overall_score"] = (
                sum(result["scores"].values()) / max(len(result["scores"]), 1)
            )
        return result

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

        total_bars = plan.get("total_bars", 0)
        message = (
            f"Based on this review, decide what needs to be revised:\n\n"
            f"Review:\n```json\n{json.dumps(review, indent=2)}\n```\n\n"
            f"Score:\n```\n{score_text}\n```\n\n"
            f"IMPORTANT: The target length is {total_bars} bars. "
            f"Do NOT add or extend bars beyond {total_bars}.\n\n"
            f"Respond with a JSON object:\n"
            f'- "iteration_complete": true if no more work needed\n'
            f'- "tasks": array of {{agent, voice, depends_on, instruction}}\n'
        )
        if extra_feedback:
            message += f"\nUser feedback: {extra_feedback}\n"

        response_text = await self._run_agent("clef-orchestrator", message, plan=plan, score_abc=score_text)
        return self._extract_json(response_text)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _run_validation(self, score_path: Path, plan_path: Path, report_path: Path) -> list[dict]:
        """Run validate_abc and return list of FAIL issues (empty if all pass).

        Returns list of {"category": ..., "voice": ..., "message": ...}.
        """
        from clef_server.tools import validate_abc

        result = validate_abc(str(score_path), str(plan_path), str(report_path))
        if "error" in result:
            logger.error("validate_abc error: %s", result["error"])
            return []

        if not report_path.exists():
            return []

        report = json.loads(report_path.read_text(encoding="utf-8"))
        fails = report.get("fails", [])
        # Filter out known artifacts
        real_fails = [f for f in fails if not f.get("known_artifact", False)]
        if real_fails:
            logger.warning(
                "Session %s: %d validation FAIL(s): %s",
                self.session_id,
                len(real_fails),
                "; ".join(f"{f['voice']}:{f['category']}" for f in real_fails),
            )
        return real_fails

    def _format_validation_feedback(self, failures: list[dict]) -> str:
        """Format validation FAIL items into a feedback string for agents."""
        if not failures:
            return ""
        lines = ["VALIDATION FAILURES (must fix before proceeding):"]
        for f in failures:
            lines.append(f"- [{f['category']}] {f['voice']}: {f['message']}")
        lines.append("You MUST fix these issues in your output. Re-check every measure's duration.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Best-of-N generation with repair
    # ------------------------------------------------------------------

    async def _generate_with_best_of_n(
        self,
        agent_name: str,
        message: str,
        plan: dict,
        plan_path: Path,
        max_rounds: int = 2,
        voice_label: str = "",
    ) -> tuple[str, int]:
        """Generate ABC with best-of-N selection and repair.

        Returns (best_abc_text, fail_count).
        """
        from clef_server.tools import fix_measure_duration

        candidates: list[dict] = []
        feedback = ""

        for round_idx in range(max_rounds):
            full_message = message
            if feedback:
                full_message = (
                    f"{message}\n\n---\n"
                    f"**上一轮验证反馈（请修正）：**\n{feedback}"
                )

            # Round 0: try two-pass generation (rhythm skeleton → pitch fill)
            abc_text = ""
            if round_idx == 0 and voice_label:
                bars = plan.get("demo_length_bars", plan.get("total_bars", 8))
                try:
                    two_pass_abc = await self._generate_two_pass(
                        agent_name, plan, plan_path, bars, voice_label,
                    )
                    if two_pass_abc:
                        abc_text = two_pass_abc
                        logger.info("Two-pass generation succeeded for %s", voice_label)
                except RecoverableAgentError:
                    logger.warning(
                        "[RECOVERABLE] Two-pass generation failed for %s round %d, falling back",
                        voice_label, round_idx,
                    )

            # Fallback to single-pass generation
            if not abc_text:
                try:
                    response = await self._run_agent(agent_name, full_message, plan=plan)
                    abc_text = self._extract_abc(response)
                except RecoverableAgentError:
                    logger.warning(
                        "[RECOVERABLE] Agent %s failed in round %d, continuing",
                        agent_name, round_idx,
                    )
                    candidates.append({
                        "round": round_idx, "abc": "",
                        "fail_count": 999, "failures": [],
                    })
                    await asyncio.sleep(5)
                    continue

            # Fallback: agent may have written ABC via write_file tool
            # even though the final text response was rejected by _extract_abc.
            if not abc_text and voice_label:
                safe_label = voice_label.replace(":", "_").replace("+", "_").replace(" ", "_")
                tmp_path = Path(self.workdir) / f"_tmp_{safe_label}.abc"
                if tmp_path.exists():
                    tmp_content = tmp_path.read_text(encoding="utf-8").strip()
                    if tmp_content and self._looks_like_abc(tmp_content):
                        abc_text = tmp_content
                        logger.info(
                            "Recovered ABC from %s (agent wrote via write_file but final response was rejected)",
                            tmp_path.name,
                        )

            if not abc_text or self._is_placeholder(abc_text):
                candidates.append({
                    "round": round_idx, "abc": abc_text or "",
                    "fail_count": 999, "failures": [],
                })
                feedback = "输出不是有效的 ABC 记谱法，请直接输出 ABC 内容。"
                continue

            # Deterministic fix
            fix_result = fix_measure_duration(abc_text)
            if fix_result["fixes"]:
                logger.info(
                    "fix_measure_duration: %d fixes in round %d",
                    len(fix_result["fixes"]), round_idx,
                )
                abc_text = fix_result["abc"]

            # Quick lint check
            lint_ok = self._quick_lint_check(abc_text, plan_path)
            if lint_ok is not True and lint_ok:
                feedback = str(lint_ok)
                candidates.append({
                    "round": round_idx, "abc": abc_text,
                    "fail_count": 100, "failures": [],
                })
                continue

            # Validate via validate_abc
            report_path = Path(self.workdir) / f"_candidate_r{round_idx}_report.json"
            failures = self._run_validation_from_abc(
                abc_text, plan_path, report_path, voice_label,
            )
            fail_count = len(failures)

            candidates.append({
                "round": round_idx, "abc": abc_text,
                "fail_count": fail_count, "failures": failures,
            })

            logger.info(
                "Best-of-N round %d: %d FAILs (agent=%s)",
                round_idx, fail_count, agent_name,
            )

            # Rate-limit pacing between best-of-N rounds
            if round_idx < max_rounds - 1:
                await asyncio.sleep(self.INTER_ROUND_DELAY)

            if fail_count == 0:
                break

            # Prepare feedback for next round
            feedback = self._format_validation_feedback(failures)

        # Select best candidate
        if not candidates:
            return "", 999
        best = min(candidates, key=lambda c: c["fail_count"])

        # If best still has failures, try repair agent
        if best["fail_count"] > 0 and best["abc"]:
            repaired = await self._attempt_repair(
                best["abc"], best["failures"], plan, plan_path, voice_label,
            )
            if repaired["fail_count"] < best["fail_count"]:
                logger.info(
                    "Repair agent improved: %d -> %d FAILs",
                    best["fail_count"], repaired["fail_count"],
                )
                best = repaired

        return best["abc"], best["fail_count"]

    def _run_validation_from_abc(
        self,
        abc_text: str,
        plan_path: Path,
        report_path: Path,
        voice_label: str = "",
    ) -> list[dict]:
        """Write ABC to temp file, validate, return failures."""
        from clef_server.tools import validate_abc as validate_tool

        safe_label = voice_label.replace(":", "_").replace("+", "_").replace(" ", "_")
        tmp_abc = Path(self.workdir) / f"_tmp_{safe_label}.abc"
        tmp_abc.write_text(abc_text, encoding="utf-8")

        try:
            result = validate_tool(str(tmp_abc), str(plan_path), str(report_path))
        except Exception as e:
            logger.warning("Validation failed: %s", e)
            return [{"category": "validation_error", "voice": voice_label, "message": str(e)}]

        if isinstance(result, dict) and "error" in result:
            return [{"category": "validation_error", "voice": voice_label, "message": result["error"]}]

        # Read report
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                fails = [
                    {"category": f.get("category", ""), "voice": f.get("voice", voice_label), "message": f.get("message", "")}
                    for f in report.get("fails", [])
                    if not f.get("known_artifact", False)
                ]
                return fails
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Report parse failed: %s", e)
                return []
        return []

    async def _attempt_repair(
        self,
        abc_text: str,
        failures: list[dict],
        plan: dict,
        plan_path: Path,
        voice_label: str = "",
    ) -> dict:
        """Attempt repair via clef-repair agent."""
        from clef_server.tools import fix_measure_duration

        if not abc_text:
            return {"abc": "", "fail_count": 999, "failures": failures}

        feedback = self._format_validation_feedback(failures)
        repair_msg = (
            f"修复以下 ABC 内容中的验证错误：\n\n"
            f"## 验证失败项\n{feedback}\n\n"
            f"## 待修复的 ABC（已在下方内联提供，请直接修改，不需要先读取任何文件）\n"
            f"```\n{abc_text}\n```\n\n"
            f"请直接修复后通过 write_file 输出完整的修正版本到 score.abc。"
            f"DO NOT call read_file — the content is already provided above."
        )

        try:
            response = await self._run_agent("clef-repair", repair_msg, plan=plan)
            repaired_abc = self._extract_abc(response)
        except Exception as e:
            logger.warning("Repair agent failed: %s", e)
            return {"abc": abc_text, "fail_count": len(failures), "failures": failures}

        if not repaired_abc:
            return {"abc": abc_text, "fail_count": len(failures), "failures": failures}

        # Deterministic fix on repaired version
        fix_result = fix_measure_duration(repaired_abc)
        if fix_result["fixes"]:
            repaired_abc = fix_result["abc"]

        # Validate repaired version
        report_path = Path(self.workdir) / "_repair_report.json"
        new_failures = self._run_validation_from_abc(
            repaired_abc, plan_path, report_path, voice_label,
        )

        return {
            "abc": repaired_abc,
            "fail_count": len(new_failures),
            "failures": new_failures,
        }

    async def _generate_two_pass(
        self,
        agent_name: str,
        plan: dict,
        plan_path: Path,
        bars: int,
        voice_label: str = "",
    ) -> str:
        """Two-pass generation: rhythm skeleton first, then pitch fill.

        Returns ABC text, or empty string if two-pass fails (caller should fallback).
        """
        from clef_server.tools import validate_rhythm_skeleton

        # Pass 1: Generate rhythm skeleton
        rhythm_msg = (
            f"Generate a {bars}-measure rhythm skeleton for {voice_label}. "
            f"M:4/4 L:1/8. Each measure MUST sum to exactly 8. "
            f"Output ONLY duration values (1,2,3,4,6,8,0.5) separated by spaces, "
            f"measures separated by |. Rests: z=1, z2=2. "
            f"Example: 2 2 2 2 | 4 4 | 2 2 1 1 2 |"
        )
        rhythm_response = await self._run_agent(agent_name, rhythm_msg, plan=plan)
        rhythm_text = self._extract_rhythm(rhythm_response)

        # Validate rhythm
        rhythm_result = validate_rhythm_skeleton(rhythm_text)
        if not rhythm_result["passed"]:
            # Retry once with feedback
            bad = [m for m in rhythm_result["measures"] if not m.get("passed")]
            bad_summary = ", ".join(
                f"M{m['measure']}={m.get('sum', 'PARSE_ERROR')}(need {m.get('target', 8)})"
                for m in bad
            )
            rhythm_msg += f"\n\nPrevious attempt had errors: {bad_summary}. Fix and output corrected skeleton."
            rhythm_response = await self._run_agent(agent_name, rhythm_msg, plan=plan)
            rhythm_text = self._extract_rhythm(rhythm_response)
            rhythm_result = validate_rhythm_skeleton(rhythm_text)

        if not rhythm_result["passed"]:
            logger.warning("Two-pass: rhythm still invalid after retry, falling back to single-pass")
            return ""

        # Pass 2: Fill pitches into validated rhythm
        pitch_msg = (
            f"Fill pitches into this validated rhythm skeleton for {voice_label}. "
            f"Key: {plan.get('key', 'C')}, Scale: {plan.get('scale', 'major')}. "
            f"Each number is a duration in L:1/8 units. Add a pitch letter before each number. "
            f"Duration 1 = just letter (e.g., c), 2 = letter+2 (e.g., c2), 4 = letter+4 (e.g., c4). "
            f"Do NOT change any durations. Output ABC notes only.\n\n"
            f"Rhythm: {rhythm_text}"
        )
        pitch_response = await self._run_agent(agent_name, pitch_msg, plan=plan)
        return self._extract_abc(pitch_response)

    def _extract_rhythm(self, response: str) -> str:
        """Extract rhythm skeleton from agent response."""
        import re as _re
        # Reject tool-call artifacts
        tool_markers = ("<|DSML|>", "<function_calls>", "</invoke>", "tool_call", "FunctionCall")
        if any(m in response for m in tool_markers):
            logger.warning("_extract_rhythm: response contains tool-call syntax, returning empty")
            return ""
        match = _re.search(r"```(?:rhythm)?\s*\n?(.*?)```", response, _re.DOTALL)
        if match:
            return match.group(1).strip()
        # Fallback: look for | separated numbers
        lines = response.strip().split("\n")
        for line in lines:
            if "|" in line and any(c.isdigit() for c in line):
                return line.strip()
        # Nothing recognizable found
        logger.warning("_extract_rhythm: no rhythm pattern found in response")
        return ""

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

        # Step 1: Generate voice parts with best-of-N validation
        from clef_server.tools import merge_abc

        for voice in generation_order:
            agent_name = self.VOICE_AGENT_MAP.get(voice)
            if not agent_name:
                continue
            voice_label = self.VOICE_MAP.get(voice, f"V:{voice}")
            demo_bars = plan.get("demo_length_bars", 8)

            voice_display = self._VOICE_DISPLAY_NAMES.get(voice, f"生成 {voice}")
            self.session.record_sub_step(voice_display, "running", agent=agent_name)

            message = (
                f"Generate a {demo_bars}-bar {voice} part as ABC notation. "
                f"Use voice label {voice_label}. Key: {plan.get('key', 'C')}, "
                f"Scale: {plan.get('scale', 'major')}, "
                f"Time: {plan.get('time_signature', '4/4')}, "
                f"BPM: {plan.get('bpm', 120)}. "
                f"This is a direction sample — focus on establishing the musical character. "
                f"Output only ABC notation."
            )

            best_abc, fail_count = await self._generate_with_best_of_n(
                agent_name=agent_name,
                message=message,
                plan=plan,
                plan_path=plan_path,
                max_rounds=2,
                voice_label=voice_label,
            )

            self._store_fragment(fragments, abc_parts, voice_label, best_abc or "")
            self.session.record_sub_step(voice_display, "done", agent=agent_name)
            logger.info("Sample voice %s: %d FAILs", voice_label, fail_count)

            # Rate-limit pacing between voice generations
            await asyncio.sleep(self.INTER_AGENT_DELAY)

        # Merge all fragments
        self.session.record_sub_step("合并声部", "running")
        merge_result = merge_abc(str(plan_path), fragments, str(score_path))
        if "error" in merge_result:
            logger.error("merge_abc failed: %s", merge_result["error"])
            raise RuntimeError(f"merge_abc failed: {merge_result['error']}")

        self._inject_midi_programs(score_path, plan)
        self.session.record_sub_step("合并声部", "done")

        # Step 2: Melody gate — review melody only up to 3 times
        self.session.record_sub_step("旋律审查", "running", agent="clef-reviewer")
        melody_agent = self.VOICE_AGENT_MAP.get("melody", "clef-composer")
        melody_label = self.VOICE_MAP.get("melody", "V:1")
        for _ in range(self.max_melody_gate_retries):
            review = await self._call_reviewer(plan, melody_only=True)
            if review.get("verdict") != "revise":
                break

            issues = review.get("issues", [])
            feedback_msg = "Issues found:\n" + "\n".join(f"- {i}" for i in issues)
            demo_bars = plan.get("demo_length_bars", 8)
            response = await self._run_agent(
                melody_agent,
                f"Revise the melody based on feedback:\n{feedback_msg}\n\n"
                f"CRITICAL: Your revised melody must be EXACTLY {demo_bars} measures. "
                f"Count your bar lines before outputting.\n"
                f"Output only the revised ABC for {melody_label}.",
                plan=plan,
                score_abc=score_path.read_text(encoding="utf-8") if score_path.exists() else "",
            )
            abc_text = self._extract_abc(response)
            fragments[melody_label] = abc_text
            merge_result = merge_abc(str(plan_path), fragments, str(score_path))
            if "error" in merge_result:
                logger.error("merge_abc (melody gate) failed: %s", merge_result["error"])
                raise RuntimeError(f"merge_abc (melody gate) failed: {merge_result['error']}")
            self._inject_midi_programs(score_path, plan)

        self.session.record_sub_step("旋律审查", "done", agent="clef-reviewer")

        # Post melody gate: validate bar count consistency across all fragments
        demo_bars = plan.get("demo_length_bars", 8)
        for label in list(fragments):
            actual = self._count_bars(fragments[label])
            if actual > demo_bars + 1:
                logger.warning("Sample fragment %s has %d bars (target %d), truncating", label, actual, demo_bars)
                fragments[label] = self._truncate_to_bars(fragments[label], demo_bars)

        # Step 3: Convert sample to MIDI (versioned by round)
        sample_round = self.session.sample_round
        sample_mid = Path(self.workdir) / f"sample_r{sample_round}.mid"
        from clef_server.tools import abc_to_midi
        self.session.record_sub_step("转换 MIDI", "running")
        midi_result = abc_to_midi(str(score_path), str(sample_mid))
        if "error" in midi_result:
            logger.error("abc_to_midi failed: %s", midi_result["error"])
            raise RuntimeError(f"abc_to_midi failed: {midi_result['error']}")
        self.session.record_sub_step("转换 MIDI", "done")

        # Step 4: Full review for confirmation data
        self.session.record_sub_step("完整审查", "running", agent="clef-reviewer")
        full_review = await self._call_reviewer(plan, melody_only=False, is_sample=True)
        review_path = Path(self.workdir) / f"review_sample_r{sample_round}.json"
        review_path.write_text(json.dumps(full_review, indent=2, ensure_ascii=False), encoding="utf-8")

        self.session.record_sub_step("完整审查", "done", agent="clef-reviewer")

        self.session.record_phase("sample", "done")
        self.session.set_awaiting_confirm(confirmation_data={
            "phase": "sample",
            "title": "试听方向小样",
            "sample_file": str(sample_mid.name),
            "review_file": str(review_path.name),
            "review": full_review,
            "sample_round": self.session.sample_round,
        })
        self.session.sample_round += 1
        logger.info("Session %s: Phase 1 (sample) done, round %d", self.session_id, self.session.sample_round)

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

            voice_display = self._VOICE_DISPLAY_NAMES.get(voice, f"生成 {voice}")
            self.session.record_sub_step(voice_display, "running", agent=agent_name)

            message = self._build_create_message(voice, plan)

            # Best-of-N generation with validation + repair
            best_abc, fail_count = await self._generate_with_best_of_n(
                agent_name=agent_name,
                message=message,
                plan=plan,
                plan_path=plan_path,
                max_rounds=2,
                voice_label=voice_label,
            )
            abc_text = best_abc

            self._store_fragment(fragments, None, voice_label, abc_text)

            self.session.record_sub_step(voice_display, "done", agent=agent_name)

            # Rate-limit pacing between voice generations
            await asyncio.sleep(self.INTER_AGENT_DELAY)

        # Validate per-voice bar counts — truncate if significantly over target
        target_bars = plan.get("total_bars", 0)
        if target_bars > 0:
            for label in list(fragments):
                actual = self._count_bars(fragments[label])
                if actual > target_bars + 1:
                    logger.warning(
                        "Session %s: Voice %s has %d bars (target %d), truncating",
                        self.session_id, label, actual, target_bars,
                    )
                    fragments[label] = self._truncate_to_bars(fragments[label], target_bars)

        # Merge all fragments
        from clef_server.tools import merge_abc
        self.session.record_sub_step("合并声部", "running")
        merge_result = merge_abc(str(plan_path), fragments, str(score_path))
        if "error" in merge_result:
            logger.error("merge_abc failed: %s", merge_result["error"])
            raise RuntimeError(f"merge_abc failed: {merge_result['error']}")

        self._inject_midi_programs(score_path, plan)
        self.session.record_sub_step("合并声部", "done")
        self.session.record_sub_step("技术验证", "running")

        # Validate and store failures for iteration phase
        report_path = Path(self.workdir) / "validation_report.json"
        failures = self._run_validation(score_path, plan_path, report_path)
        self._validation_failures = failures  # Persist for iterate phase

        if failures:
            # Repair agent approach for post-merge failures
            logger.info("Phase create: %d FAILs after merge, attempting repair", len(failures))
            score_abc = score_path.read_text(encoding="utf-8")
            repaired = await self._attempt_repair(
                abc_text=score_abc,
                failures=failures,
                plan=plan,
                plan_path=plan_path,
            )
            if repaired["fail_count"] < len(failures):
                logger.info(
                    "Repair improved: %d -> %d FAILs",
                    len(failures), repaired["fail_count"],
                )
                score_path.write_text(repaired["abc"], encoding="utf-8")
                self._inject_midi_programs(score_path, plan)
                # Re-validate
                self._validation_failures = self._run_validation(score_path, plan_path, report_path)
                # Re-enforce bar limits after repair
                if target_bars > 0:
                    for label in list(fragments):
                        actual = self._count_bars(fragments[label])
                        if actual > target_bars + 1:
                            fragments[label] = self._truncate_to_bars(fragments[label], target_bars)
                            merge_result = merge_abc(str(plan_path), fragments, str(score_path))
                            if "error" not in merge_result:
                                self._inject_midi_programs(score_path, plan)
            else:
                logger.info("Repair did not improve, keeping original")

        self.session.record_sub_step("技术验证", "done")

        # Convert to MIDI (versioned)
        base_mid = Path(self.workdir) / "base_r1.mid"
        from clef_server.tools import abc_to_midi
        self.session.record_sub_step("转换 MIDI", "running")
        midi_result = abc_to_midi(str(score_path), str(base_mid))
        if "error" in midi_result:
            logger.error("abc_to_midi failed: %s", midi_result["error"])
            raise RuntimeError(f"abc_to_midi failed: {midi_result['error']}")
        self.session.record_sub_step("转换 MIDI", "done")

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

        from clef_server.tools import merge_abc

        plan_path = Path(self.workdir) / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        score_path = Path(self.workdir) / "score.abc"

        for round_num in range(1, self.max_iteration_rounds + 1):
            # Compress accumulated iteration history before each round
            self._iteration_history = self._microcompact_messages(self._iteration_history)

            self.session.iteration_count = round_num
            self.session.record_sub_step(
                f"迭代轮次 {round_num}/{self.max_iteration_rounds}", "running"
            )

            # Full review
            self.session.record_sub_step("完整审查", "running", agent="clef-reviewer")
            review = await self._call_reviewer(plan, melody_only=False)
            iter_review_path = Path(self.workdir) / f"review_iter_r{round_num}.json"
            iter_review_path.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
            self.session.record_sub_step("完整审查", "done", agent="clef-reviewer")

            # Rate-limit pacing between reviewer and leader
            await asyncio.sleep(self.INTER_AGENT_DELAY)

            # Track review as a tool-like message for microcompact
            self._iteration_history.append({
                "role": "tool",
                "name": "validate_abc",
                "content": json.dumps(review),
            })

            # Leader decides tasks
            self.session.record_sub_step("任务调度", "running", agent="clef-leader")
            leader_decision = await self._call_leader(plan, review, extra_feedback=extra_feedback)
            self.session.record_sub_step("任务调度", "done", agent="clef-leader")
            tasks = leader_decision.get("tasks", [])

            if leader_decision.get("iteration_complete", False) or not tasks:
                logger.info(
                    "Session %s: iteration round %d — no tasks, stopping",
                    self.session_id, round_num,
                )
                break

            # Sort by depends_on for execution order
            completed_agents: set[str] = set()
            tasks_sorted = sorted(tasks, key=lambda t: str(t.get("depends_on", "")))
            for task in tasks_sorted:
                raw_dep = task.get("depends_on", "")
                # Normalize: LLM may return string, list, or null
                if isinstance(raw_dep, list):
                    deps = [str(d) for d in raw_dep if d]
                else:
                    deps = [str(raw_dep)] if raw_dep else []
                # Normalize dep names (e.g. "composer" → "clef-composer")
                deps = [d if d.startswith("clef-") else f"clef-{d}" for d in deps]
                if any(d not in completed_agents for d in deps):
                    continue  # skip if dependency not yet completed

                agent_name = task.get("agent", "clef-composer")
                # Normalize: LLM may return "composer" instead of "clef-composer"
                if not agent_name.startswith("clef-"):
                    agent_name = f"clef-{agent_name}"
                if agent_name not in self._agent_defs:
                    logger.warning("Unknown agent %r from leader, skipping task", agent_name)
                    continue
                instruction = task.get("instruction", "Revise based on review feedback.")

                # Append review issues so the agent has full context
                review_issues = review.get("issues", [])
                if review_issues:
                    issues_text = "\n".join(f"- {i}" for i in review_issues)
                    instruction += f"\n\nReview issues to address:\n{issues_text}"

                # Append validation failures if any
                if self._validation_failures:
                    instruction += "\n\n" + self._format_validation_feedback(self._validation_failures)

                current_score = score_path.read_text(encoding="utf-8") if score_path.exists() else ""
                task_label = f"执行任务 ({agent_name})"
                self.session.record_sub_step(task_label, "running", agent=agent_name)
                response = await self._run_agent(
                    agent_name,
                    instruction,
                    plan=plan,
                    score_abc=current_score,
                )
                abc_text = self._extract_abc(response)

                voice = task.get("voice", "melody")
                voice_label = self.VOICE_MAP.get(voice, f"V:{voice}")

                # Replace voice content via merge_abc instead of appending
                all_fragments = self._parse_voice_blocks(current_score)
                if "+" in voice_label:
                    # Handle rhythm multi-voice (V:3+V:4)
                    sub_labels = [l.strip() for l in voice_label.split("+")]
                    rhythm_blocks = self._parse_voice_blocks(f"RHYTHM_PLACEHOLDER\n{abc_text}\n")
                    for sub_label in sub_labels:
                        if sub_label in rhythm_blocks:
                            all_fragments[sub_label] = rhythm_blocks[sub_label]
                else:
                    all_fragments[voice_label] = abc_text

                merge_result = merge_abc(str(plan_path), all_fragments, str(score_path))
                if "error" in merge_result:
                    logger.error("merge_abc (iteration) failed: %s", merge_result["error"])
                    raise RuntimeError(f"merge_abc (iteration) failed: {merge_result['error']}")

                # Enforce bar count — truncate if agent added extra bars
                target_bars = plan.get("total_bars", 0)
                if target_bars > 0:
                    current_score = score_path.read_text(encoding="utf-8")
                    actual = self._count_bars(current_score)
                    if actual > target_bars + 1:
                        logger.warning(
                            "Session %s: After %s revision, score has %d bars (target %d), truncating",
                            self.session_id, agent_name, actual, target_bars,
                        )
                        truncated = self._truncate_to_bars(current_score, target_bars)
                        score_path.write_text(truncated, encoding="utf-8")

                completed_agents.add(agent_name)
                self.session.record_sub_step(task_label, "done", agent=agent_name)

                # Rate-limit pacing between sequential agent tasks
                await asyncio.sleep(self.INTER_AGENT_DELAY)

                # Refresh score for next task in this round
                current_score = score_path.read_text(encoding="utf-8") if score_path.exists() else ""

            # Validate + export versioned MIDI after each iteration round
            self._inject_midi_programs(score_path, plan)
            report_path = Path(self.workdir) / f"validation_report_iter{round_num}.json"
            failures = self._run_validation(score_path, plan_path, report_path)
            self._validation_failures = failures

            # Export versioned MIDI for this iteration round
            iter_mid = Path(self.workdir) / f"base_r{round_num + 1}.mid"
            from clef_server.tools import abc_to_midi
            midi_result = abc_to_midi(str(score_path), str(iter_mid))
            if "error" in midi_result:
                logger.warning("abc_to_midi failed for iteration round %d: %s", round_num, midi_result["error"])

            self.session.record_sub_step(
                f"迭代轮次 {round_num}/{self.max_iteration_rounds}", "done"
            )

        # C6: Set confirmation_data with review + iteration count before advancing
        self.session.record_phase("iterate", "done")
        logger.info(
            "Session %s: Phase 3 (iterate) done, %d rounds",
            self.session_id, self.session.iteration_count,
        )

        if self.skip_review:
            # Fast test mode — skip review, go directly to express
            logger.info("Session %s: skip_review=True, skipping review phase", self.session_id)
            await self._phase_express()
        else:
            final_review = await self._call_reviewer(plan, melody_only=False)
            final_review_path = Path(self.workdir) / f"review_final_r{self.session.iteration_count}.json"
            final_review_path.write_text(json.dumps(final_review, indent=2, ensure_ascii=False), encoding="utf-8")
            confirmation_data = {
                "phase": "review",
                "title": "试听审核",
                "review": final_review,
                "iteration_count": self.session.iteration_count,
                "output_file": "final.mid",
            }
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

        # Find latest versioned base MIDI (base_r1.mid, base_r2.mid, ...)
        base_mids = sorted(Path(self.workdir).glob("base_r*.mid"))
        base_mid = base_mids[-1] if base_mids else None

        if not base_mid or not base_mid.exists():
            self.session.record_phase("express", "done", error="base_r*.mid not found")
            self.session.set_done()
            logger.warning("Session %s: base_r*.mid missing, skipping expression injection", self.session_id)
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

        self.session.record_sub_step("生成表现力方案", "running", agent="clef-orchestrator")
        response = await self._run_agent("clef-orchestrator", message, plan=plan)
        expression_plan = self._extract_json(response)

        self.session.record_sub_step("生成表现力方案", "done", agent="clef-orchestrator")

        # Save expression plan
        expr_plan_path = Path(self.workdir) / "expression_plan.json"
        expr_plan_path.write_text(
            json.dumps(expression_plan, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Inject expression into MIDI (versioned)
        iter_count = self.session.iteration_count or 1
        output_path = Path(self.workdir) / f"final_r{iter_count}.mid"

        from clef_server.tools import inject_expression
        self.session.record_sub_step("注入表现力数据", "running")
        inject_result = inject_expression(str(base_mid), str(expr_plan_path), str(output_path))
        if isinstance(inject_result, dict) and "error" in inject_result:
            logger.error("inject_expression failed: %s", inject_result["error"])
            self.session.record_phase("express", "done", error=inject_result["error"])
            self.session.set_done()
            return

        self.session.record_sub_step("注入表现力数据", "done")

        self.session.record_phase("express", "done")
        self.session.set_done(output_files=[str(output_path.relative_to(Path(self.workdir)))])
        logger.info("Session %s: Phase 4 (express) done, output=%s", self.session_id, output_path)
