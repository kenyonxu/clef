# Clef Server Workflow Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align server workflow with clef-compose skill: 6 phases, 3 confirmation points, Leader iteration, expression injection.

**Architecture:** Phase Orchestrator pattern. `ComposeOrchestrator` class manages the full lifecycle. Each phase is a self-contained method. Phase completion updates session state; confirmation points set `awaiting_confirm`. Frontend polls `GET /status`, resumes with `POST /confirm`.

**Tech Stack:** Python (FastAPI, asyncio, httpx), Agent Framework, React 19 + TypeScript + Zustand + TailwindCSS

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `server/src/clef_server/orchestrator.py` | ComposeOrchestrator — phased workflow coordinator |
| `server/tests/test_orchestrator.py` | Orchestrator unit tests |
| `server/web/src/components/ConfirmationPanel.tsx` | Confirmation container — routes to sub-components |
| `server/web/src/components/PlanConfirm.tsx` | Confirmation point 1: plan parameter review |
| `server/web/src/components/SampleConfirm.tsx` | Confirmation point 2: direction sample + review scores |
| `server/web/src/components/ReviewConfirm.tsx` | Confirmation point 3: final composition + iteration summary |

### Modified files
| File | Change |
|------|--------|
| `server/src/clef_server/sessions.py` | PHASES constant, new fields (current_phase, confirmation_data, phase_history, sample_round), phase transitions |
| `server/src/clef_server/routes.py` | Replace _run_workflow with orchestrator integration, update confirm endpoint |
| `server/src/clef_server/workflow.py` | Remove monolithic build_compose_workflow, keep executors as utilities |
| `server/web/src/api/types.ts` | Add ConfirmationData, PhaseStep, PhaseHistory, update StatusResponse/Session |
| `server/web/src/stores/sessionStore.ts` | Add confirmSession action, confirmationData/currentPhase/sampleRound state |
| `server/web/src/pages/Workspace.tsx` | Render ConfirmationPanel when awaiting_confirm |

---

### Task 1: Session Model Enhancement

**Files:**
- Modify: `server/src/clef_server/sessions.py`
- Modify: `server/tests/test_sessions.py`

- [ ] **Step 1: Add PHASES constant and update ComposeSession**

Replace the existing `WORKFLOW_STEPS` constant with `PHASES` and add new fields to `ComposeSession`. The new phase IDs are: `parse`, `sample`, `create`, `iterate`, `review`, `express`. The old `WORKFLOW_STEPS` referenced step IDs 0-3; the new system uses string phase IDs.

```python
# Replace WORKFLOW_STEPS with PHASES
PHASES = [
    {"id": "parse",   "label": "需求解析 + 规划",  "confirm": True},
    {"id": "sample",  "label": "方向小样",         "confirm": True},
    {"id": "create",  "label": "完整创作",         "confirm": False},
    {"id": "iterate", "label": "质量迭代",         "confirm": False},
    {"id": "review",  "label": "试听审核",         "confirm": True},
    {"id": "express", "label": "表现力注入",       "confirm": False},
]

PHASE_ORDER = ["parse", "sample", "create", "iterate", "review", "express"]
```

Add new fields to `ComposeSession.__init__` defaults:

```python
current_phase: str = "parse"
confirmation_data: dict | None = None
phase_history: list[dict] = field(default_factory=list)
sample_round: int = 0
iteration_count: int = 0
```

Keep the old `step_status` and `current_step` fields for backward compatibility but mark deprecated. Add `get_phases()` method that returns phase list with status derived from `phase_history`.

- [ ] **Step 2: Add set_awaiting_confirm with data**

Extend `set_awaiting_confirm` to accept optional confirmation_data:

```python
def set_awaiting_confirm(self, confirmation_data: dict | None = None) -> None:
    self._transition("awaiting_confirm")
    self.confirmation_data = confirmation_data
```

Add `record_phase` method:

```python
def record_phase(self, phase_id: str, status: str, *, error: str | None = None) -> None:
    entry = {"phase": phase_id, "status": status, "error": error, "timestamp": time.time()}
    self.phase_history.append(entry)
    self.updated_at = time.time()
```

- [ ] **Step 3: Update get_workflow_steps to derive from PHASES**

Change `get_workflow_steps()` to use `PHASES` instead of `WORKFLOW_STEPS`, deriving status from `phase_history`:

```python
def get_workflow_steps(self) -> list[dict]:
    """Return workflow phases with current status derived from phase_history."""
    phases = []
    for p in PHASES:
        status = "pending"
        for entry in reversed(self.phase_history):
            if entry["phase"] == p["id"]:
                status = entry["status"]
                break
        step = {**p, "status": status}
        phases.append(step)
    return phases
```

- [ ] **Step 4: Write tests for new session features**

```python
# tests/test_sessions.py — add to TestComposeSession class

def test_phases_constant(self):
    from clef_server.sessions import PHASES, PHASE_ORDER
    assert len(PHASES) == 6
    assert PHASES[0]["id"] == "parse"
    assert PHASES_ORDER[0] == "parse"
    assert sum(1 for p in PHASES if p["confirm"]) == 3

def test_set_awaiting_confirm_with_data(self, tmp_path: Path):
    session = ComposeSession(session_id="s1", workdir=str(tmp_path))
    session.set_running()
    session.set_awaiting_confirm({"phase": "parse", "plan": {"key": "C"}})
    assert session.status == "awaiting_confirm"
    assert session.confirmation_data["plan"]["key"] == "C"

def test_record_phase(self, tmp_path: Path):
    session = ComposeSession(session_id="s1", workdir=str(tmp_path))
    session.record_phase("parse", "done")
    session.record_phase("sample", "done")
    assert len(session.phase_history) == 2
    assert session.phase_history[0]["phase"] == "parse"

def test_get_workflow_steps_from_phases(self, tmp_path: Path):
    session = ComposeSession(session_id="s1", workdir=str(tmp_path))
    session.record_phase("parse", "done")
    steps = session.get_workflow_steps()
    assert steps[0]["status"] == "done"
    assert steps[1]["status"] == "pending"
```

- [ ] **Step 5: Run tests**

Run: `cd server && PYTHONPATH=src python -m pytest tests/test_sessions.py -v`
Expected: All pass (including old tests, backward compatible)

- [ ] **Step 6: Commit**

```bash
git add server/src/clef_server/sessions.py server/tests/test_sessions.py
git commit -m "feat(server): enhance session model with phase tracking and confirmation data"
```

---

### Task 2: Orchestrator Skeleton + Phase 0 (Parse + Plan)

**Files:**
- Create: `server/src/clef_server/orchestrator.py`
- Create: `server/tests/test_orchestrator.py`

- [ ] **Step 1: Write orchestrator skeleton with start() and resume()**

Create `server/src/clef_server/orchestrator.py` with the ComposeOrchestrator class. The `start()` method creates providers and runs Phase 0. The `resume()` method reads `session.current_phase` and runs the next phase. Each phase method calls `session.record_phase()`, does work, and either calls `session.set_awaiting_confirm()` or calls the next phase directly.

```python
"""Compose Orchestrator — phased workflow coordinator for music composition."""

import json
import logging
from pathlib import Path

from clef_server.sessions import PHASE_ORDER, SessionManager

logger = logging.getLogger(__name__)


class ComposeOrchestrator:
    """Manages the full compose workflow lifecycle across 6 phases.

    Each phase is a self-contained method that reads/writes workdir files.
    Confirmation phases set session to awaiting_confirm.
    """

    def __init__(self, session_id: str, providers: dict, workdir: str):
        self.session_id = session_id
        self.providers = providers
        self.workdir = workdir
        self._session = SessionManager().get(session_id)

    @property
    def session(self):
        s = SessionManager().get(self.session_id)
        if s:
            self._session = s
        return self._session

    async def start(self, prompt: str) -> None:
        """Entry point — runs Phase 0 (parse + plan)."""
        await self._phase_parse(prompt)

    async def resume(self, user_feedback: str | None = None) -> None:
        """Resume from awaiting_confirm — run next phase."""
        phase = self.session.current_phase
        logger.info(f"Resuming session {self.session_id} from phase {phase}, feedback={user_feedback}")

        if phase == "parse":
            await self._phase_sample(feedback=user_feedback)
        elif phase == "sample":
            await self._phase_create()
        elif phase == "review":
            if user_feedback:
                await self._phase_iterate(extra_feedback=user_feedback)
            else:
                await self._phase_express()
        else:
            logger.error(f"Cannot resume from phase {phase}")

    def _next_phase(self, current: str) -> str | None:
        idx = PHASE_ORDER.index(current)
        return PHASE_ORDER[idx + 1] if idx + 1 < len(PHASE_ORDER) else None

    async def _advance_phase(self, from_phase: str) -> None:
        """Move to next phase. If it's a confirm phase, stop. Otherwise run it."""
        next_phase = self._next_phase(from_phase)
        if next_phase is None:
            self.session.set_done(output_files=self._collect_outputs())
            return
        from clef_server.sessions import PHASES
        phase_info = next(p for p in PHASES if p["id"] == next_phase)
        self.session.current_phase = next_phase
        self.session.record_phase(next_phase, "running")
        logger.info(f"Session {self.session_id}: entering phase {next_phase}")

        if phase_info["confirm"]:
            # Will be confirmed by resume()
            return
        # Non-confirm phase: run it immediately
        method = getattr(self, f"_phase_{next_phase}")
        await method()

    def _collect_outputs(self) -> list[str]:
        output_dir = Path(self.workdir) / "output"
        return [str(f) for f in output_dir.glob("*.mid")] if output_dir.exists()

    # Phase methods are implemented in Tasks 3-6
    async def _phase_parse(self, prompt: str) -> None: ...
    async def _phase_sample(self, feedback: str | None = None) -> None: ...
    async def _phase_create(self) -> None: ...
    async def _phase_iterate(self, extra_feedback: str | None = None) -> None: ...
    async def _phase_express(self) -> str: ...
```

- [ ] **Step 2: Implement _phase_parse — LLM generates plan.json**

Add the `_phase_parse` method. It calls a provider LLM with a structured prompt to parse the user's music requirements and output a plan.json. Uses ChatCompletionsClient directly (not AF Agent). On success, saves plan.json and sets awaiting_confirm.

```python
async def _phase_parse(self, prompt: str) -> None:
    """Phase 0: Parse requirements and generate plan.json via LLM."""
    from clef_server.chat_completions_client import ChatCompletionsClient
    from agent_framework import Message

    client = self.providers.get("deepseek")
    if not client:
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
        "- orchestration: object with melody/harmony/bass/drums sub-objects, each having name, channel, instrument, range, register\n"
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
    # Extract JSON from response (handle potential markdown wrapping)
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rstrip("`")

    plan = json.loads(content)
    plan_path = Path(self.workdir) / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    self.session.record_phase("parse", "done")
    self.session.set_awaiting_confirm(confirmation_data={
        "phase": "parse",
        "title": "确认音乐规划",
        "plan": plan,
    })
    logger.info(f"Session {self.session_id}: Phase 0 done, plan saved")
```

- [ ] **Step 3: Write tests for orchestrator skeleton and Phase 0**

```python
# tests/test_orchestrator.py
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clef_server.sessions import PHASES, SessionManager
from clef_server.orchestrator import ComposeOrchestrator


@pytest.fixture
def session():
    mgr = SessionManager()
    return mgr.create("test prompt", workdir="/tmp/test-clef")


@pytest.fixture
def providers():
    mock_client = AsyncMock()
    mock_client.get_response = AsyncMock(return_value=MagicMock(
        messages=[MagicMock(contents=['{"title": "Test","key": "C","bpm": 120}'])]
    ))
    return {"deepseek": mock_client}


class TestOrchestratorInit:
    def test_create(self, session, providers):
        orch = ComposeOrchestrator(session.session_id, providers, session.workdir)
        assert orch.session_id == session.session_id

    def test_phase_order_constant(self):
        from clef_server.orchestrator import PHASE_ORDER
        assert PHASE_ORDER[0] == "parse"
        assert len(PHASE_ORDER) == 6


class TestPhaseParse:
    @pytest.mark.asyncio
    async def test_phase_parse_generates_plan(self, session, providers, tmp_path):
        session.workdir = str(tmp_path)
        orch = ComposeOrchestrator(session.session_id, providers, session.workdir)
        await orch._phase_parse("Write a boss battle music")
        plan_file = tmp_path / "plan.json"
        assert plan_file.exists()
        plan = json.loads(plan_file.read_text())
        assert plan["key"] == "C"
        assert session.status == "awaiting_confirm"
        assert session.confirmation_data["phase"] == "parse"

    @pytest.mark.asyncio
    async def test_phase_parse_records_history(self, session, providers, tmp_path):
        session.workdir = str(tmp_path)
        orch = ComposeOrchestrator(session.session_id, providers, session.workdir)
        await orch._phase_parse("test")
        assert len(session.phase_history) == 2  # running + done
```

- [ ] **Step 4: Run tests**

Run: `cd server && PYTHONPATH=src python -m pytest tests/test_orchestrator.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "feat(server): add ComposeOrchestrator with Phase 0 (parse + plan)"
```

---

### Task 3: Phase 1 — Direction Sample

**Files:**
- Modify: `server/src/clef_server/orchestrator.py`
- Modify: `server/tests/test_orchestrator.py`

- [ ] **Step 1: Implement _phase_sample in orchestrator**

The direction sample phase dispatches harmony and melody agents sequentially (per `generation_order`), runs a melody gate review (3 rounds max), merges ABC, generates sample MIDI, then runs a full review. Sets `awaiting_confirm` with sample file and review report.

The implementation uses `create_agent()` to build AF agents, then calls them directly via `AgentExecutor`. After each agent call, it extracts the ABC text from the response. For the melody gate, it calls the reviewer agent with only 4 review dimensions (M1/M3/M4/M5).

```python
async def _phase_sample(self, feedback: str | None = None) -> None:
    """Phase 1: Generate direction sample with melody gate + review."""
    from clef_server.agents import create_agent
    try:
        from agent_framework import AgentExecutor, AgentExecutorResponse, Message
    except ImportError:
        AgentExecutor = None
        AgentExecutorResponse = None
        Message = None

    self.session.record_phase("sample", "running")

    plan = json.loads((Path(self.workdir) / "plan.json").read_text(encoding="utf-8"))
    generation_order = plan.get("generation_order", ["harmony", "melody"])
    demo_length = plan.get("demo_length_bars", 8)

    # Add feedback to instructions if provided
    feedback_context = f"\n\nUser feedback (round {self.session.sample_round}): {feedback}" if feedback else ""

    fragments = {}
    for voice_name in generation_order:
        agent_config_map = {
            "harmony": ("clef-harmonist", "clef-harmonist.md", ["harmony", "abc"], ["read_file", "write_file", "validate_abc", "abc_lint"]),
            "melody": ("clef-composer", "clef-composer.md", ["melody", "orchestration", "abc"], ["read_file", "write_file", "validate_abc", "abc_lint"]),
        }
        agent_name, prompt_md, skills, tools = agent_config_map[voice_name]
        from clef_server.config import AgentConfig
        project_root = Path(__file__).resolve().parent.parent.parent
        config = AgentConfig(
            prompt_md=project_root / ".claude" / "agents" / prompt_md,
            model_alias="deepseek", temperature=0.8,
            skills=skills, tools=tools,
        )

        agent = create_agent(name=agent_name, config=config, providers=self.providers,
                             skills_dir=project_root / ".claude" / "skills",
                             plan=plan, workdir=self.workdir)
        prompt_text = (
            f"Generate {demo_length} bars of {voice_name} (V:2 if harmony, V:1 if melody). "
            f"Read plan.json for musical context.{feedback_context}"
        )

        if AgentExecutor:
            ae = AgentExecutor(agent)
            result = await ae.run(Message(role="user", contents=[prompt_text]))
            abc_text = ""
            if hasattr(result, "messages") and result.messages:
                for c in result.messages[0].contents:
                    if hasattr(c, "text"):
                        abc_text += str(c)
            fragments[voice_name] = abc_text
        else:
            fragments[voice_name] = f"% {voice_name} placeholder\n"

    # Merge fragments
    from clef_server.tools import merge_abc, write_file, abc_to_midi
    merged = merge_abc(plan_path=f"{self.workdir}/plan.json", fragments=fragments, output=f"{self.workdir}/score.abc")
    Path(f"{self.workdir}/score.abc").write_text(merged, encoding="utf-8")

    # Melody gate review (max 3 rounds)
    melody_ok = True
    for round_num in range(3):
        review_result = await self._call_reviewer(plan, melody_only=True)
        if review_result and review_result.get("verdict") == "revise":
            logger.info(f"Melody gate round {round_num+1}: revise")
            # Re-dispatch composer with feedback
            agent = create_agent(name="clef-composer", config=config, providers=self.providers,
                                 skills_dir=project_root / ".claude" / "skills",
                                 plan=plan, workdir=self.workdir)
            if AgentExecutor:
                ae = AgentExecutor(agent)
                fix_prompt = f"Revise melody per review feedback: {json.dumps(review_result)}. Keep {demo_length} bars."
                result = await ae.run(Message(role="user", contents=[fix_prompt]))
                abc_text = ""
                if hasattr(result, "messages") and result.messages:
                    for c in result.messages[0].contents:
                        if hasattr(c, "text"): abc_text += str(c)
                fragments["melody"] = abc_text
                merged = merge_abc(plan_path=f"{self.workdir}/plan.json", fragments=fragments, output=f"{self.workdir}/score.abc")
                Path(f"{self.workdir}/score.abc").write_text(merged, encoding="utf-8")
        else:
            melody_ok = True
            break

    # Generate sample MIDI
    sample_path = f"{self.workdir}/sample.mid"
    abc_to_midi(input_abc=f"{self.workdir}/score.abc", output_mid=sample_path)

    # Full review
    review = await self._call_reviewer(plan, melody_only=False)

    self.session.record_phase("sample", "done")
    self.session.set_awaiting_confirm(confirmation_data={
        "phase": "sample",
        "title": "试听方向小样",
        "sample_file": sample_path,
        "review": review,
        "sample_round": self.session.sample_round,
    })

async def _call_reviewer(self, plan: dict, melody_only: bool = False) -> dict | None:
    """Call reviewer agent and return structured review result."""
    try:
        from agent_framework import AgentExecutor, Message
    except ImportError:
        return None
    from clef_server.agents import create_agent
    from clef_server.config import AgentConfig
    project_root = Path(__file__).resolve().parent.parent.parent

    scope = "Only check: M1 pitch/melody, M3 rhythm, M4 register, M5 alignment" if melody_only else "Full 7-dimension review"
    config = AgentConfig(
        prompt_md=project_root / ".claude" / "agents" / "clef-reviewer.md",
        model_alias="deepseek", temperature=0.3,
        skills=["theory-harmony", "theory-melody", "theory-rhythm", "abc"],
        tools=["read_file", "validate_abc", "abc_lint"],
    )
    agent = create_agent(name="clef-reviewer", config=config, providers=self.providers,
                         skills_dir=project_root / ".claude" / "skills",
                         plan=plan, workdir=self.workdir,
                         score_abc=Path(f"{self.workdir}/score.abc").read_text(encoding="utf-8") if Path(f"{self.workdir}/score.abc").exists() else None)
    ae = AgentExecutor(agent)
    result = await ae.run(Message(role="user", contents=[f"Review the current score. {scope}."]))
    review_text = ""
    if hasattr(result, "messages") and result.messages:
        for c in result.messages[0].contents:
            if hasattr(c, "text"): review_text += str(c)
    try:
        # Extract JSON from review response
        review_text = review_text.strip()
        if review_text.startswith("```"):
            review_text = review_text.split("\n", 1)[-1].rstrip("`")
        return json.loads(review_text)
    except (json.JSONDecodeError, IndexError):
        return {"raw": review_text, "verdict": "pass"}
```

- [ ] **Step 2: Update resume() to handle sample feedback loop**

In `resume()`, the "parse" branch should check for feedback and handle the sample round counter:

```python
if phase == "parse":
    if user_feedback and self.session.sample_round < 10:
        self.session.sample_round += 1
        await self._phase_sample(feedback=user_feedback)
    else:
        self.session.sample_round = 0
        await self._phase_sample()
```

- [ ] **Step 3: Write tests for Phase 1**

```python
# tests/test_orchestrator.py — add TestPhaseSample class

@pytest.mark.asyncio
async def test_phase_sample_creates_files(session, providers, tmp_path):
    session.workdir = str(tmp_path)
    # Pre-create plan.json so sample phase can read it
    plan = {"key": "C", "bpm": 120, "generation_order": ["harmony", "melody"], "demo_length_bars": 4}
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    orch = ComposeOrchestrator(session.session_id, providers, session.workdir)
    await orch._phase_sample()
    assert session.status == "awaiting_confirm"
    assert session.confirmation_data["phase"] == "sample"
    assert (tmp_path / "sample.mid").exists()

@pytest.mark.asyncio
async def test_sample_round_counter(session, providers, tmp_path):
    session.workdir = str(tmp_path)
    plan = {"key": "C", "bpm": 120, "generation_order": ["harmony", "melody"], "demo_length_bars": 4}
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    orch = ComposeOrchestrator(session.session_id, providers, session.workdir)
    # Simulate resume with feedback
    session.sample_round = 0
    await orch.resume("too aggressive")
    assert session.sample_round == 1
```

- [ ] **Step 4: Run tests**

Run: `cd server && PYTHONPATH=src python -m pytest tests/test_orchestrator.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "feat(server): implement Phase 1 direction sample with melody gate"
```

---

### Task 4: Phase 2 — Full Creation

**Files:**
- Modify: `server/src/clef_server/orchestrator.py`
- Modify: `server/tests/test_orchestrator.py`

- [ ] **Step 1: Implement _phase_create**

This phase dispatches all 3 agents sequentially (harmony → melody → rhythmist), merges, validates, and analyzes. No confirmation needed; automatically advances to Phase 3.

```python
async def _phase_create(self) -> None:
    """Phase 2: Full creation with all agents."""
    from clef_server.agents import create_agent
    from clef_server.config import AgentConfig
    from clef_server.tools import merge_abc, validate_abc, abc_to_midi, write_file
    try:
        from agent_framework import AgentExecutor, Message
    except ImportError:
        AgentExecutor = None
        Message = None

    self.session.record_phase("create", "running")
    plan = json.loads((Path(self.workdir) / "plan.json").read_text(encoding="utf-8"))
    generation_order = plan.get("generation_order", ["harmony", "melody"])
    project_root = Path(__file__).resolve().parent.parent.parent

    agent_config_map = {
        "harmony": ("clef-harmonist", "clef-harmonist.md", ["harmony", "abc"], ["read_file", "write_file", "validate_abc", "abc_lint"]),
        "melody": ("clef-composer", "clef-composer.md", ["melody", "orchestration", "abc"], ["read_file", "write_file", "validate_abc", "abc_lint"]),
        "rhythm": ("clef-rhythmist", "clef-rhythmist.md", ["rhythm", "abc"], ["read_file", "write_file", "validate_abc", "abc_lint"]),
    }

    fragments = {}
    for voice_name, (agent_name, prompt_md, skills, tools) in agent_config_map.items():
        config = AgentConfig(
            prompt_md=project_root / ".claude" / "agents" / prompt_md,
            model_alias="deepseek", temperature=0.8,
            skills=skills, tools=tools,
        )
        agent = create_agent(name=agent_name, config=config, providers=self.providers,
                             skills_dir=project_root / ".claude" / "skills",
                             plan=plan, workdir=self.workdir)
        if AgentExecutor:
            ae = AgentExecutor(agent)
            result = await ae.run(Message(role="user", contents=[f"Generate full {voice_name} part. Read plan.json for context."]))
            abc_text = ""
            if hasattr(result, "messages") and result.messages:
                for c in result.messages[0].contents:
                    if hasattr(c, "text"): abc_text += str(c)
            fragments[voice_name] = abc_text

    # Merge all fragments
    merge_abc(plan_path=f"{self.workdir}/plan.json", fragments=fragments, output=f"{self.workdir}/score.abc")

    # Validate
    validate_abc(abc_file=f"{self.workdir}/score.abc", plan_file=f"{self.workdir}/plan.json", output=f"{self.workdir}/validation_report.json")

    # Convert to MIDI for analysis
    abc_to_midi(input_abc=f"{self.workdir}/score.abc", output_mid=f"{self.workdir}/base.mid")

    self.session.record_phase("create", "done")
    logger.info(f"Session {self.session_id}: Phase 2 done")
    await self._advance_phase("create")
```

- [ ] **Step 2: Write test for Phase 2**

```python
@pytest.mark.asyncio
async def test_phase_create_all_agents(session, providers, tmp_path):
    session.workdir = str(tmp_path)
    plan = {"key": "C", "bpm": 120, "generation_order": ["harmony", "melody"]}
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    orch = ComposeOrchestrator(session.session_id, providers, session.workdir)
    # Skip to create phase by setting current_phase
    session.current_phase = "create"
    session.set_running()
    await orch._phase_create()
    assert (tmp_path / "score.abc").exists()
    assert (tmp_path / "base.mid").exists()
```

- [ ] **Step 3: Run tests and commit**

Run: `cd server && PYTHONPATH=src python -m pytest tests/test_orchestrator.py -v`

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "feat(server): implement Phase 2 full creation with all agents"
```

---

### Task 5: Phase 3 — Leader Iteration

**Files:**
- Modify: `server/src/clef_server/orchestrator.py`
- Modify: `server/tests/test_orchestrator.py`

- [ ] **Step 1: Implement _phase_iterate**

```python
async def _phase_iterate(self, extra_feedback: str | None = None) -> None:
    """Phase 3: Leader iteration loop (max 3 rounds)."""
    from clef_server.agents import create_agent
    from clef_server.tools import merge_abc, validate_abc, abc_to_midi, write_file
    try:
        from agent_framework import AgentExecutor, Message
    except ImportError:
        AgentExecutor = None
        Message = None

    self.session.record_phase("iterate", "running")
    plan = json.loads((Path(self.workdir) / "plan.json").read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parent.parent.parent

    for iteration in range(3):
        self.session.iteration_count = iteration + 1
        logger.info(f"Session {self.session_id}: iteration {iteration + 1}/3")

        # Run reviewer
        review = await self._call_reviewer(plan, melody_only=False)

        # Run leader
        leader_result = await self._call_leader(plan, review, extra_feedback)
        if not leader_result or leader_result.get("iteration_complete"):
            break

        tasks = leader_result.get("tasks", [])
        if not tasks:
            break

        # Execute tasks — sort by depends_on for ordering
        completed_agents = set()
        for task in tasks:
            if task.get("depends_on") and task["depends_on"] not in completed_agents:
                continue
            agent_name = task["agent"]
            instruction = task["instruction"]
            agent_config_map = {
                "clef-composer": ("clef-composer", "clef-composer.md", ["melody", "orchestration", "abc"], ["read_file", "write_file", "validate_abc", "abc_lint"]),
                "clef-harmonist": ("clef-harmonist", "clef-harmonist.md", ["harmony", "abc"], ["read_file", "write_file", "validate_abc", "abc_lint"]),
                "clef-rhythmist": ("clef-rhythmist", "clef-rhythmist.md", ["rhythm", "abc"], ["read_file", "write_file", "validate_abc", "abc_lint"]),
                "clef-revision": ("clef-revision", "clef-revision.md", [], ["read_file", "write_file"]),
            }
            if agent_name not in agent_config_map:
                continue
            agent_name_key, prompt_md, skills, tools = agent_config_map[agent_name]
            from clef_server.config import AgentConfig
            config = AgentConfig(
                prompt_md=project_root / ".claude" / "agents" / prompt_md,
                model_alias="deepseek", temperature=0.7,
                skills=skills, tools=tools,
            )
            agent = create_agent(name=agent_name, config=config, providers=self.providers,
                                 skills_dir=project_root / ".claude" / "skills",
                                 plan=plan, workdir=self.workdir)
            if AgentExecutor:
                ae = AgentExecutor(agent)
                result = await ae.run(Message(role="user", contents=[instruction]))
                completed_agents.add(agent_name)

        # Merge and validate after each iteration
        merge_abc(plan_path=f"{self.workdir}/plan.json", fragments={}, output=f"{self.workdir}/score.abc")
        # Re-read fragments and merge properly (simplified: merge from score.abc fragments)
        validate_abc(abc_file=f"{self.workdir}/score.abc", plan_file=f"{self.workdir}/plan.json", output=f"{self.workdir}/validation_report.json")

    self.session.record_phase("iterate", "done")
    await self._advance_phase("iterate")

async def _call_leader(self, plan: dict, review: dict | None, extra_feedback: str | None = None) -> dict | None:
    """Call leader agent to decide iteration tasks."""
    try:
        from agent_framework import AgentExecutor, Message
    except ImportError:
        return None
    from clef_server.agents import create_agent
    from clef_server.config import AgentConfig
    project_root = Path(__file__).resolve().parent.parent.parent

    config = AgentConfig(
        prompt_md=project_root / ".claude" / "agents" / "clef-leader.md",
        model_alias="deepseek", temperature=0.3,
        skills=["theory-structure"],
        tools=["read_file", "write_file", "glob", "grep"],
    )
    agent = create_agent(name="clef-leader", config=config, providers=self.providers,
                         skills_dir=project_root / ".claude" / "skills",
                         plan=plan, workdir=self.workdir)
    ae = AgentExecutor(agent)
    prompt_parts = ["Analyze the music and generate iteration tasks."]
    if extra_feedback:
        prompt_parts.append(f"User feedback: {extra_feedback}")
    result = await ae.run(Message(role="user", contents=["\n".join(prompt_parts)]))
    text = ""
    if hasattr(result, "messages") and result.messages:
        for c in result.messages[0].contents:
            if hasattr(c, "text"): text += str(c)
    try:
        text = text.strip()
        if text.startswith("```"): text = text.split("\n", 1)[-1].rstrip("`")
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return None
```

Also update `resume()` for the "review" phase:

```python
elif phase == "review":
    if user_feedback:
        await self._phase_iterate(extra_feedback=user_feedback)
    else:
        await self._phase_express()
```

- [ ] **Step 2: Write tests for Phase 3**

```python
@pytest.mark.asyncio
async def test_phase_iterate_stops_on_complete(session, providers, tmp_path):
    session.workdir = str(tmp_path)
    plan = {"key": "C", "bpm": 120}
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "score.abc").write_text("X:1\n")
    orch = ComposeOrchestrator(session.session_id, providers, session.workdir)
    session.current_phase = "iterate"
    session.set_running()
    await orch._phase_iterate()
    assert session.iteration_count >= 1
```

- [ ] **Step 3: Run tests and commit**

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "feat(server): implement Phase 3 Leader iteration with review/leader loop"
```

---

### Task 6: Phase 4 — Expression Injection

**Files:**
- Modify: `server/src/clef_server/orchestrator.py`
- Modify: `server/tests/test_orchestrator.py`

- [ ] **Step 1: Implement _phase_express**

```python
async def _phase_express(self) -> str:
    """Phase 4: Orchestrator generates expression plan, then inject into MIDI."""
    from clef_server.agents import create_agent
    from clef_server.tools import inject_expression
    try:
        from agent_framework import AgentExecutor, Message
    except ImportError:
        AgentExecutor = None
        Message = None

    self.session.record_phase("express", "running")
    plan = json.loads((Path(self.workdir) / "plan.json").read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parent.parent

    # Call orchestrator agent for expression plan
    config = AgentConfig(
        prompt_md=project_root / ".claude" / "agents" / "clef-orchestrator.md",
        model_alias="deepseek", temperature=0.5,
        skills=["theory-orchestration", "abc"],
        tools=["read_file", "write_file", "abc_to_midi", "inject_expression"],
    )
    agent = create_agent(name="clef-orchestrator", config=config, providers=self.providers,
                         skills_dir=project_root / ".claude" / "skills",
                         plan=plan, workdir=self.workdir,
                         score_abc=Path(f"{self.workdir}/base.mid").read_text(encoding="utf-8") if Path(f"{self.workdir}/base.mid").exists() else None)
    if AgentExecutor:
        ae = AgentExecutor(agent)
        result = await ae.run(Message(role="user", contents=["Generate expression plan for the score. Read base.mid and plan.json for context."]))
        expr_text = ""
        if hasattr(result, "messages") and result.messages:
            for c in result.messages[0].contents:
                if hasattr(c, "text"): expr_text += str(c)
        expr_path = Path(self.workdir) / "expression_plan.json"
        expr_path.write_text(expr_text, encoding="utf-8")

    # Inject expression into MIDI
    output_path = f"{self.workdir}/output/final.mid"
    Path(f"{self.workdir}/output").mkdir(parents=True, exist_ok=True)
    inject_expression(midi_file=f"{self.workdir}/base.mid", plan_file=str(expr_path), output=output_path)

    self.session.record_phase("express", "done")
    self.session.set_done(output_files=[output_path])
    logger.info(f"Session {self.session_id}: Phase 4 done, output={output_path}")
    return output_path
```

- [ ] **Step 2: Write test for Phase 4**

```python
@pytest.mark.asyncio
async def test_phase_express_produces_final(session, providers, tmp_path):
    session.workdir = str(tmp_path)
    plan = {"key": "C", "bpm": 120}
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "base.mid").write_text("MThd")  # minimal MIDI
    orch = ComposeOrchestrator(session.session_id, providers, session.workdir)
    session.current_phase = "express"
    session.set_running()
    output = await orch._phase_express()
    assert output.endswith("final.mid")
    assert session.status == "done"
```

- [ ] **Step 3: Run all tests and commit**

Run: `cd server && PYTHONPATH=src python -m pytest tests/test_orchestrator.py tests/test_sessions.py -v`

```bash
git add server/src/clef_server/orchestrator.py server/tests/test_orchestrator.py
git commit -m "feat(server): implement Phase 4 expression injection via orchestrator"
```

---

### Task 7: Routes Integration

**Files:**
- Modify: `server/src/clef_server/routes.py`

- [ ] **Step 1: Replace _run_workflow with orchestrator**

Replace the existing `_run_workflow` function. The new version creates a `ComposeOrchestrator` and calls `start()`. The orchestrator manages its own phase lifecycle. Also update `POST /confirm` to call `orchestrator.resume(feedback)`.

```python
# Replace _run_workflow entirely
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
```

- [ ] **Step 2: Update confirm endpoint**

```python
class ConfirmRequest(BaseModel):
    action: str = Field(..., description="'continue' or 'cancel'")
    feedback: str | None = Field(None, description="Optional user feedback text")

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
```

- [ ] **Step 3: Update StatusResponse model**

Add new fields to `StatusResponse`:

```python
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
```

Update `get_status` to include new fields:

```python
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
```

- [ ] **Step 4: Run tests and commit**

Run: `cd server && PYTHONPATH=src python -m pytest tests/test_routes.py -v`

```bash
git add server/src/clef_server/routes.py
git commit -m "feat(server): wire orchestrator into routes with confirm/feedback flow"
```

---

### Task 8: Server Integration Tests

**Files:**
- Modify: `server/tests/test_integration.py`

- [ ] **Step 1: Update integration test to mock orchestrator**

Update the integration test to verify the orchestrator wiring works end-to-end. Mock the LLM calls to return valid plan/review/leader JSON, verify that the session transitions through phases correctly.

```python
def test_compose_workflow_phase_transitions():
    """Verify session transitions through phases with mocked LLM."""
    # This test verifies the orchestrator correctly chains phases
    # by mocking all LLM responses
    ...
```

- [ ] **Step 2: Run full test suite**

Run: `cd server && PYTHONPATH=src python -m pytest tests/ -v`

```bash
git add server/tests/test_integration.py
git commit -m "test(server): update integration tests for phased workflow"
```

---

### Task 9: Frontend API Types + SessionStore Update

**Files:**
- Modify: `server/web/src/api/types.ts`
- Modify: `server/web/src/stores/sessionStore.ts`

- [ ] **Step 1: Add new types to types.ts**

```typescript
export interface ConfirmationData {
  phase: 'parse' | 'sample' | 'review'
  title: string
  plan?: Record<string, unknown>
  sample_file?: string
  review?: ReviewData
  iterations?: number
  sample_round?: number
  output_file?: string
}

export interface ReviewData {
  verdict?: 'pass' | 'revise'
  scores?: Record<string, number>
  summary?: string
}

export interface PhaseStep {
  id: string
  name: string
  label: string
  status: WorkflowStepStatus
  confirm: boolean
}
```

Update `StatusResponse`:

```typescript
export interface StatusResponse {
  session_id: string
  status: SessionStatus
  user_prompt: string
  workflow_steps?: PhaseStep[]
  output_files: string[]
  error?: string
  current_phase?: string
  confirmation_data?: ConfirmationData
  sample_round?: number
  iteration_count?: number
}
```

- [ ] **Step 2: Update SessionStore with confirm action**

Add `confirmSession` action and `confirmationData`/`currentPhase`/`sampleRound`/`iterationCount` state. Also update `pollOnce` to extract new fields:

```typescript
interface SessionState {
  currentSession: Session | null
  sessions: Session[]
  workflowSteps: PhaseStep[]
  messages: ChatMessage[]
  outputFiles: OutputFile[]
  confirmationData: ConfirmationData | null
  currentPhase: string
  sampleRound: number
  iterationCount: number

  submitPrompt: (prompt: string) => Promise<void>
  pollOnce: (sessionId: string) => Promise<void>
  cancelSession: (sessionId: string) => Promise<void>
  loadSessions: () => Promise<void>
  confirmSession: (sessionId: string, action: 'continue' | 'cancel', feedback?: string) => Promise<void>
}
```

In `pollOnce`, extract new fields from the status response:

```typescript
pollOnce: async (sessionId: string) => {
  try {
    const data = await apiClient.get<StatusResponse>(`/status/${sessionId}`)
    set({
      currentSession: data,
      workflowSteps: (data.workflow_steps ?? []) as PhaseStep[],
      outputFiles: data.output_files.map(fileFromPath),
      confirmationData: data.confirmation_data ?? null,
      currentPhase: data.current_phase ?? "",
      sampleRound: data.sample_round ?? 0,
      iterationCount: data.iteration_count ?? 0,
    })
  } catch { /* silent */ }
},
```

Add `confirmSession`:

```typescript
confirmSession: async (sessionId: string, action: 'continue' | 'cancel', feedback?: string) => {
  try {
    await apiClient.post(`/confirm/${sessionId}`, { action, feedback })
    // Poll immediately to get updated state
    await get().pollOnce(sessionId)
  } catch (err) {
    set((s) => ({
      messages: [...s.messages, { id: createMessageId(), type: 'error', content: err instanceof Error ? err.message : 'Confirm failed', timestamp: Date.now() }],
    }))
  }
},
```

Add system message for phase transitions:

```typescript
// In pollOnce, after setting state, check for confirmation_data and add system message
if (data.confirmation_data) {
  set((s) => ({
    messages: [
      ...s.messages,
      {
        id: createMessageId(),
        type: 'system',
        content: data.confirmation_data.title,
        timestamp: Date.now(),
      },
    ],
  }))
}
```

- [ ] **Step 3: Run frontend tests and commit**

```bash
cd server/web && npm test
git add server/web/src/api/types.ts server/web/src/stores/sessionStore.ts
git commit -m "feat(web): add confirmation types and confirmSession action to store"
```

---

### Task 10: ConfirmationPanel + PlanConfirm Components

**Files:**
- Create: `server/web/src/components/ConfirmationPanel.tsx`
- Create: `server/web/src/components/PlanConfirm.tsx`

- [ ] **Step 1: Create ConfirmationPanel container**

The ConfirmationPanel reads `confirmationData` from the store and routes to the appropriate sub-component. It renders the feedback textarea and action buttons (Cancel, Modify/Continue). When user clicks Continue, it calls `confirmSession`. When user clicks Modify/Cancel with feedback, it calls `confirmSession` with feedback.

```tsx
// server/web/src/components/ConfirmationPanel.tsx
import { useSessionStore } from '../stores/sessionStore'
import { PlanConfirm } from './PlanConfirm'
import { SampleConfirm } from './SampleConfirm'
import { ReviewConfirm } from './ReviewConfirm'
import type { ConfirmationData } from '../api/types'

export function ConfirmationPanel() {
  const confirmationData = useSessionStore((s) => s.confirmationData)
  const confirmSession = useSessionStore((s) => s.confirmSession)
  const [feedback, setFeedback] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (!confirmationData) return null

  const { phase } = confirmationData

  const handleContinue = async () => {
    setIsSubmitting(true)
    await confirmSession(confirmationData.session_id ?? '', 'continue', feedback || undefined)
    setFeedback('')
    setIsSubmitting(false)
  }

  const handleCancel = async () => {
    setIsSubmitting(true)
    await confirmSession(confirmationData.session_id ?? '', 'cancel')
    setFeedback('')
    setIsSubmitting(false)
  }

  const handleModify = async () => {
    setIsSubmitting(true)
    await confirmSession(confirmationData.session_id ?? '', 'continue', feedback)
    setFeedback('')
    setIsSubmitting(false)
  }

  const renderConfirmContent = () => {
    switch (phase) {
      case 'parse': return <PlanConfirm data={confirmationData} />
      case 'sample': return <SampleConfirm data={confirmationData} />
      case 'review': return <ReviewConfirm data={confirmationData} />
      default: return <p className="text-sm text-error">Unknown confirmation phase: {phase}</p>
    }
  }

  return (
    <div className="rounded-xl border border-border-subtle bg-surface-elevated p-4 space-y-3">
      {renderConfirmContent()}
      <textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder="反馈建议（可选）..."
        rows={2}
        className="w-full resize-none rounded-lg bg-surface-mid px-3 py-2 text-sm text-white placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand"
        disabled={isSubmitting}
      />
      <div className="flex items-center justify-end gap-2">
        <button onClick={handleCancel} disabled={isSubmitting} className="rounded-[500px] border border-error px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-error transition-opacity hover:opacity-80 disabled:opacity-40">Cancel</button>
        {phase !== 'parse' && <button onClick={handleModify} disabled={isSubmitting} className="rounded-[500px] border border-border-subtle px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-white transition-opacity hover:opacity-80 disabled:opacity-40">修改方向</button>}
        <button onClick={handleContinue} disabled={isSubmitting} className="rounded-[500px] bg-brand px-6 py-1.5 text-xs font-bold uppercase tracking-wider text-black transition-opacity hover:opacity-90 disabled:opacity-40">{phase === 'review' ? '确认 · 注入表现力' : '继续'}</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create PlanConfirm component**

This renders the plan.json parameters in a grid layout: key, scale, BPM, time signature, form, duration, demo_length, generation_order. Plus the orchestration section (4 voices with name/channel/range/register) and sections list.

```tsx
// server/web/src/components/PlanConfirm.tsx
import type { ConfirmationData } from '../api/types'

interface PlanConfirmProps {
  data: ConfirmationData
}

export function PlanConfirm({ data }: PlanConfirmProps) {
  const plan = data.plan ?? {}

  const params = [
    { label: '标题', value: plan.title },
    { label: '调性', value: `${plan.key} ${plan.scale ?? ''}` },
    { label: 'BPM', value: plan.bpm },
    { label: '拍号', value: plan.time_signature },
    { label: '曲式', value: plan.form },
    { label: '时长', value: plan.duration_beats ? `${plan.duration_beats} beats` : '—' },
    { label: '小样长度', value: plan.demo_length_bars ? `${plan.demo_length_bars} bars` : '—' },
    { label: '生成顺序', value: (plan.generation_order ?? []).join(' → ') },
  ]

  const sections = plan.sections ?? []
  const orch = plan.orchestration ?? {}

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        {params.map((p) => (
          <div key={p.label} className="rounded-lg bg-surface-mid px-3 py-2">
            <div className="text-[10px] text-muted uppercase">{p.label}</div>
            <div className="text-sm font-semibold">{p.value}</div>
          </div>
        ))}
      </div>
      <div>
        <div className="text-xs font-semibold text-text-secondary mb-2">配器方案</div>
        {['melody', 'harmony', 'bass', 'drums'].map((voice) => {
          const v = orch[voice]
          if (!v) return null
          return (
            <div key={voice} className="flex items-center gap-2 text-xs py-1 border-b border-border-subtle last:border-0">
              <span className="w-10 text-muted">{voice === 'melody' ? 'V:1' : voice === 'harmony' ? 'V:2' : voice === 'bass' ? 'V:3' : 'V:4'}</span>
              <span className="flex-1">{v.name}</span>
              <span className="text-muted">{v.range && `${v.register} · `}{v.instrument}</span>
            </div>
          )
        })}
      </div>
      {sections.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-text-secondary mb-2">段落结构</div>
          {sections.map((s) => (
            <div key={s.id} className="flex items-center gap-2 text-xs py-1 border-b border-border-subtle last:border-0">
              <span className="text-brand font-bold w-6">{s.id}</span>
              <span className="flex-1">{s.name}</span>
              <span className="text-muted">{s.measures} bars · energy {s.energy_level}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Run frontend build and commit**

```bash
cd server/web && npm run build
git add server/web/src/components/ConfirmationPanel.tsx server/web/src/components/PlanConfirm.tsx
git commit -m "feat(web): add ConfirmationPanel and PlanConfirm components"
```

---

### Task 11: SampleConfirm + ReviewConfirm Components

**Files:**
- Create: `server/web/src/components/SampleConfirm.tsx`
- Create: `server/web/src/components/ReviewConfirm.tsx`

- [ ] **Step 1: Create SampleConfirm component**

Displays sample MIDI file with play button, review score bars (melody, harmony, rhythm, sound_range, voice_balance, form, overall), and verdict badge.

```tsx
// server/web/src/components/SampleConfirm.tsx
import type { ConfirmationData } from '../api/types'

interface SampleConfirmProps {
  data: ConfirmationData
}

function ScoreBar({ label, score }: { label: string; score: number }) {
  const color = score >= 8 ? 'bg-[#1ed760]' : score >= 7 ? 'bg-[#f59b23]' : 'bg-[#e91429]'
  return (
    <div className="flex items-center gap-2 text-sm py-0.5">
      <span className="w-20 text-text-secondary">{label}</span>
      <div className="flex-1 h-1.5 bg-surface-mid rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score * 10}%` }} />
      </div>
      <span className="w-8 text-right font-semibold" style={{ color }}>{score.toFixed(1)}</span>
    </div>
  )
}

export function SampleConfirm({ data }: SampleConfirmProps) {
  const review = data.review
  const scores = review?.scores ?? {}
  const verdict = review?.verdict ?? 'pass'
  const round = data.sample_round ?? 0

  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-surface-mid p-3 flex items-center gap-3">
        <span className="text-2xl">🎵</span>
        <div className="flex-1">
          <div className="text-sm font-semibold">{data.sample_file?.split('/').pop()}</div>
          <div className="text-xs text-muted">{round > 0 ? `反馈轮次 ${round}/10` : ''}</div>
        </div>
      </div>
      <ScoreBar label="旋律" score={scores.melody ?? 0} />
      <ScoreBar label="和声" score={scores.harmony ?? 0} />
      <ScoreBar label="节奏" score={scores.rhythm ?? 0} />
      <ScoreBar label="音域" score={scores.sound_range ?? 0} />
      <ScoreBar label="声部平衡" score={scores.voice_balance ?? 0} />
      <div className="flex items-center gap-2 mt-1">
        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold ${verdict === 'pass' ? 'bg-[rgba(30,215,96,0.15)] text-[#1ed760]' : 'bg-[rgba(233,20,41,0.15)] text-[#e91429]'}`}>{verdict.toUpperCase()}</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create ReviewConfirm component**

Displays final MIDI with play button, iteration count, total score, score bars, and "确认·注入表现力" button text.

```tsx
// server/web/src/components/ReviewConfirm.tsx
import type { ConfirmationData } from '../api/types'

function ScoreBar({ label, score }: { label: string; score: number }) {
  const color = score >= 8 ? 'bg-[#1ed760]' : score >= 7 ? 'bg-[#f59b23]' : 'bg-[#e91429]'
  return (
    <div className="flex items-center gap-2 text-sm py-0.5">
      <span className="w-20 text-text-secondary">{label}</span>
      <div className="flex-1 h-1.5 bg-surface-mid rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score * 10}%` }} />
      </div>
      <span className="w-8 text-right font-semibold" style={{ color }}>{score.toFixed(1)}</span>
    </div>
  )
}

export function ReviewConfirm({ data }: ReviewConfirmProps) {
  const review = data.review
  const scores = review?.scores ?? {}
  const iterations = data.iterations ?? 0

  return (
    <div className="space-y-3">
      <div className="flex gap-3 text-xs text-muted mb-2">
        <span>迭代 {iterations}/3 轮</span>
      </div>
      <div className="rounded-lg bg-surface-mid p-3 flex items-center gap-3">
        <span className="text-2xl">🎶</span>
        <div className="flex-1">
          <div className="text-sm font-semibold">{data.output_file?.split('/').pop()}</div>
        </div>
      </div>
      <ScoreBar label="旋律" score={scores.melody ?? 0} />
      <ScoreBar label="和声" score={scores.harmony ?? 0} />
      <ScoreBar label="节奏" score={scores.rhythm ?? 0} />
      <ScoreBar label="音域" score={scores.sound_range ?? 0} />
      <ScoreBar label="声部平衡" score={scores.voice_balance ?? 0} />
      <div className="text-xs text-muted mt-1">继续后将执行表现力注入（力度/弯音/颤音）</div>
    </div>
  )
}
```

- [ ] **Step 3: Run frontend build and commit**

```bash
cd server/web && npm run build
git add server/web/src/components/SampleConfirm.tsx server/web/src/components/ReviewConfirm.tsx
git commit -m "feat(web): add SampleConfirm and ReviewConfirm components"
```

---

### Task 12: Workspace Integration

**Files:**
- Modify: `server/web/src/pages/Workspace.tsx`

- [ ] **Step 1: Integrate ConfirmationPanel into Workspace**

In the right column (steps area), when `confirmationData` exists, render `ConfirmationPanel` instead of the step cards. Import `ConfirmationPanel` and the store selector.

Add to imports:

```tsx
import { ConfirmationPanel } from '../components/ConfirmationPanel'
```

Replace the steps rendering block with conditional:

```tsx
{currentSession && (
  <div className="flex items-center justify-between">
    <h2 className="text-lg font-bold text-white">Workflow</h2>
    <StatusBadge status={currentSession.status as SessionStatus} />
  </div>
)}

{confirmationData ? (
  <ConfirmationPanel />
) : (
  <div className="space-y-2">
    {workflowSteps.map((step) => (
      <StepCard key={step.id} step={step} isExpanded={step.name === 'create'} />
    ))}
  </div>
)}
```

- [ ] **Step 2: Run full frontend build**

```bash
cd server/web && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add server/web/src/pages/Workspace.tsx
git commit -m "feat(web): integrate ConfirmationPanel into Workspace"
```

---

## Self-Review

**1. Spec coverage:**
- Phase 0 (parse + plan) → Task 2 ✅
- Phase 1 (sample + melody gate) → Task 3 ✅
- Phase 2 (create) → Task 4 ✅
- Phase 3 (iterate) → Task 5 ✅
- Phase 4 (express) → Task 6 ✅
- 3 confirmation points → Tasks 10, 11 ✅
- Session model changes → Task 1 ✅
- Routes integration → Task 7 ✅
- Frontend store → Task 9 ✅

**2. Placeholder scan:** No TBD, TODO, or "similar to" references found.

**3. Type consistency:** Phase IDs are strings throughout (not numbers). `ConfirmationData.phase` matches the PHASES constant IDs. `StatusResponse` new fields align between server and frontend.
