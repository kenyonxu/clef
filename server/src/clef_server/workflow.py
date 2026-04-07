"""Compose workflow -- AF graph workflow for multi-agent music composition.

MVP workflow (Phase 1):
  prompt_builder → [fan-out: composer, harmonist, rhythmist] → extractors → [fan-in: merge] → inject

Type flow:
  PromptBuilder(ComposeRequest) → str (fan-out) → AgentExecutor(str) → AgentExecutorResponse
  AgentExecutorResponse → VoiceFragmentExtractor → VoiceFragment
  list[VoiceFragment] → MergeExecutor → str (merged ABC)
  str → InjectExecutor → workflow output (midi path)
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clef_server.agents import create_agent
from clef_server.config import AgentConfig

COMPOSE_WORKFLOW_ID = "clef-compose"

# AF imports with fallback for test environments
try:
    from agent_framework import (
        AgentExecutor,
        AgentExecutorResponse,
        Executor,
        Message,
        WorkflowBuilder,
        WorkflowContext,
        handler,
    )
    from agent_framework._workflows._agent_executor import AgentExecutorResponse as _AER
    AgentExecutorResponse = _AER
    from typing_extensions import Never
except ImportError:

    class _FakeWorkflowBuilder:
        """Callable mock that chains method calls and returns itself."""

        def __init__(self, *_args, **_kwargs):
            pass

        def __getattr__(self, _name):
            return self

        def __call__(self, *_args, **_kwargs):
            return self

    class _FallbackExecutor:
        def __init__(self, id: str, **kwargs):
            self.id = id

    Executor = _FallbackExecutor

    class _WorkflowContext:
        """Minimal fallback that supports subscript for type hints."""
        def __class_getitem__(cls, item):
            return cls

    WorkflowContext = _WorkflowContext
    WorkflowBuilder = _FakeWorkflowBuilder
    AgentExecutor = None
    AgentExecutorResponse = None
    Message = object
    handler = lambda f: f
    Never = None


# === Data types for inter-executor communication ===
# These flow between custom executors only, never directly into AgentExecutor.

@dataclass
class ComposeRequest:
    user_prompt: str
    workdir: str
    plan: dict | None = None


@dataclass
class VoiceFragment:
    agent_name: str
    abc_content: str


@dataclass
class MergedScore:
    score_abc: str
    plan: dict
    workdir: str


# === Deterministic Executors ===

class PromptBuilderExecutor(Executor):
    """Receives ComposeRequest, builds a prompt string, fan-outs to 3 agents.

    Output: str -- a prompt string containing the plan JSON and user instructions,
    suitable for AgentExecutor's from_str handler.
    """

    def __init__(self, workdir: str, id: str = "prompt_builder"):
        super().__init__(id=id)
        self._workdir = workdir

    @handler
    async def build(self, message: ComposeRequest, ctx: WorkflowContext[str]) -> None:
        plan = message.plan or {"title": message.user_prompt, "status": "parsed"}
        prompt = self._build_prompt(message.user_prompt, plan, message.workdir)
        await ctx.send_message(prompt)

    @staticmethod
    def _build_prompt(user_prompt: str, plan: dict, workdir: str) -> str:
        parts = [
            f"# Composition Request\n\n{user_prompt}\n",
            f"# Plan\n\n```json\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n```\n",
            f"# Working Directory\n\n{workdir}\n",
        ]
        return "\n".join(parts)


class VoiceFragmentExtractor(Executor):
    """Receives AgentExecutorResponse, extracts ABC text into VoiceFragment.

    This is the adapter that bridges AF's AgentExecutorResponse to our
    internal VoiceFragment dataclass.
    """

    def __init__(self, agent_name: str, workdir: str = "", id: str = "extract_fragment"):
        super().__init__(id=id)
        self._agent_name = agent_name
        self._workdir = workdir

    @handler
    async def extract(self, message: Any, ctx: WorkflowContext[VoiceFragment]) -> None:
        abc_content = message.agent_response.text if hasattr(message, "agent_response") else str(message)
        await ctx.send_message(VoiceFragment(agent_name=self._agent_name, abc_content=abc_content))


class MergeExecutor(Executor):
    """Receives list[VoiceFragment] (fan-in), merges into one ABC, outputs str.

    The merged ABC string is sent downstream as plain str for the next executor.
    """

    def __init__(self, workdir: str = "", id: str = "merge"):
        super().__init__(id=id)
        self._workdir = workdir

    @handler
    async def merge(self, message: list[VoiceFragment], ctx: WorkflowContext[str]) -> None:
        from clef_server.tools import merge_abc, write_file

        plan: dict = {}
        fragments: dict[str, str] = {}

        for frag in message:
            voice_label = self._extract_voice_label(frag.abc_content, frag.agent_name)
            fragments[voice_label] = frag.abc_content

        workdir = self._workdir
        plan_path = f"{workdir}/plan.json"
        write_file(path=plan_path, content=json.dumps(plan, ensure_ascii=False))
        output_path = f"{workdir}/score.abc"
        merge_abc(plan=plan_path, fragments=fragments, output=output_path)

        score_abc = Path(output_path).read_text(encoding="utf-8") if Path(output_path).exists() else ""
        await ctx.send_message(score_abc)

    @staticmethod
    def _extract_voice_label(abc: str, agent_name: str) -> str:
        match = re.search(r"V:\s*(\d+)", abc)
        if match:
            return f"V:{match.group(1)}"
        name_to_voice = {
            "clef-composer": "V:1",
            "clef-harmonist": "V:2",
            "clef-rhythmist": "V:3",
        }
        return name_to_voice.get(agent_name, "V:1")


class InjectExecutor(Executor):
    """Receives str (merged ABC), converts to MIDI, yields workflow output.

    Uses WorkflowContext[Never, str] -- only yields output, never sends downstream.
    """

    def __init__(self, workdir: str = "", id: str = "inject"):
        super().__init__(id=id)
        self._workdir = workdir

    @handler
    async def inject(self, message: str, ctx: WorkflowContext) -> None:
        from clef_server.tools import write_file, abc_to_midi

        workdir = self._workdir
        score_abc = message

        score_path = f"{workdir}/score.abc"
        write_file(path=score_path, content=score_abc)

        midi_path = f"{workdir}/output/final.mid"
        Path(f"{workdir}/output").mkdir(parents=True, exist_ok=True)
        abc_to_midi(input_abc=score_path, output_mid=midi_path)

        await ctx.yield_output(midi_path)


# === Workflow Builder ===

def build_compose_workflow(
    providers: dict,
    plan: dict | None = None,
    workdir: str = "",
    skills_dir: Path | None = None,
) -> Any:
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    if skills_dir is None:
        skills_dir = project_root / ".claude" / "skills"

    agents_dir = project_root / ".claude" / "agents"
    agent_configs: dict[str, AgentConfig] = {
        "clef-composer": AgentConfig(
            prompt_md=agents_dir / "clef-composer.md",
            model_alias="deepseek", temperature=0.8,
            skills=["melody", "orchestration", "abc"],
            tools=["read_file", "write_file", "validate_abc", "abc_lint"],
        ),
        "clef-harmonist": AgentConfig(
            prompt_md=agents_dir / "clef-harmonist.md",
            model_alias="deepseek", temperature=0.8,
            skills=["harmony", "abc"],
            tools=["read_file", "write_file", "validate_abc", "abc_lint"],
        ),
        "clef-rhythmist": AgentConfig(
            prompt_md=agents_dir / "clef-rhythmist.md",
            model_alias="deepseek", temperature=0.7,
            skills=["rhythm", "abc"],
            tools=["read_file", "write_file", "validate_abc", "abc_lint"],
        ),
    }

    # Build the workflow graph
    prompt_builder = PromptBuilderExecutor(workdir=workdir, id="prompt_builder")
    merge_exec = MergeExecutor(workdir=workdir, id="merge")
    inject_exec = InjectExecutor(workdir=workdir, id="inject")

    # Create agent executors (mocked in tests)
    agent_executors: dict = {}
    extractors: dict = {}
    for name in agent_configs:
        try:
            agent = create_agent(
                name=name,
                config=agent_configs[name],
                providers=providers,
                skills_dir=skills_dir,
                plan=plan,
                workdir=workdir,
            )
            ae = AgentExecutor(agent)
            agent_executors[name] = ae
        except (RuntimeError, ImportError):
            # AF not available -- create mock executors for testing
            class MockAgentExecutor(Executor):
                def __init__(self, name_: str, id_: str):
                    self.id = id_
                    self._name = name_
            ae = MockAgentExecutor(name, f"agent_{name}")
            agent_executors[name] = ae

        extractors[name] = VoiceFragmentExtractor(
            agent_name=name, workdir=workdir, id=f"extract_{name}"
        )

    workflow = (
        WorkflowBuilder(start_executor=prompt_builder, name=COMPOSE_WORKFLOW_ID)
        # fan-out: prompt → 3 agents
        .add_fan_out_edges(prompt_builder, [
            agent_executors["clef-composer"],
            agent_executors["clef-harmonist"],
            agent_executors["clef-rhythmist"],
        ])
        # agent outputs → extractors
        .add_edge(agent_executors["clef-composer"], extractors["clef-composer"])
        .add_edge(agent_executors["clef-harmonist"], extractors["clef-harmonist"])
        .add_edge(agent_executors["clef-rhythmist"], extractors["clef-rhythmist"])
        # fan-in: extractors → merge
        .add_fan_in_edges(
            [extractors["clef-composer"], extractors["clef-harmonist"], extractors["clef-rhythmist"]],
            merge_exec,
        )
        # merge → inject
        .add_edge(merge_exec, inject_exec)
        .build()
    )

    return workflow
