"""Compose workflow — AF graph workflow for multi-agent music composition.

MVP workflow (Phase 1):
  parse → plan → [fan-out: composer, harmonist, rhythmist] → merge → review → express
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
        Executor,
        Message,
        WorkflowBuilder,
        WorkflowContext,
        handler,
    )
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

    Executor = object

    class _WorkflowContext:
        """Minimal fallback that supports subscript for type hints."""
        def __class_getitem__(cls, item):
            return cls

    WorkflowContext = _WorkflowContext
    WorkflowBuilder = _FakeWorkflowBuilder
    AgentExecutor = None
    Message = object
    handler = lambda f: f
    Never = None


# === Data types for inter-executor communication ===

@dataclass
class ComposeRequest:
    user_prompt: str
    workdir: str
    plan: dict | None = None


@dataclass
class PlanResult:
    plan: dict
    workdir: str


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

class ParseExecutor(Executor):
    def __init__(self, workdir: str, id: str = "parse"):
        self.id = id
        self._workdir = workdir

    @handler
    async def process(self, message: ComposeRequest, ctx: WorkflowContext[PlanResult]) -> None:
        plan = message.plan or {"title": message.user_prompt, "status": "parsed"}
        await ctx.send_message(PlanResult(plan=plan, workdir=message.workdir))


class PlanExecutor(Executor):
    def __init__(self, id: str = "plan"):
        self.id = id

    @handler
    async def process(self, message: PlanResult, ctx: WorkflowContext[PlanResult]) -> None:
        await ctx.send_message(message)


class VoiceFragmentExtractor(Executor):
    def __init__(self, agent_name: str, workdir: str = "", id: str = "extract_fragment"):
        self.id = id
        self._agent_name = agent_name
        self._workdir = workdir

    @handler
    async def process(self, message: Any, ctx: WorkflowContext[VoiceFragment]) -> None:
        abc_content = message.agent_response.text if hasattr(message, 'agent_response') else str(message)
        await ctx.send_message(VoiceFragment(agent_name=self._agent_name, abc_content=abc_content))


class MergeExecutor(Executor):
    def __init__(self, id: str = "merge"):
        self.id = id

    @handler
    async def process(self, message: list[VoiceFragment], ctx: WorkflowContext[MergedScore]) -> None:
        from clef_server.tools import merge_abc, write_file

        plan: dict = {}
        workdir = ""
        fragments: dict[str, str] = {}

        for frag in message:
            voice_label = self._extract_voice_label(frag.abc_content, frag.agent_name)
            fragments[voice_label] = frag.abc_content
            if not workdir and frag.agent_name:
                workdir = getattr(frag, "_workdir", "")

        plan_path = f"{workdir}/plan.json"
        write_file(path=plan_path, content=json.dumps(plan, ensure_ascii=False))
        output_path = f"{workdir}/score.abc"
        merge_abc(plan=plan_path, fragments=fragments, output=output_path)

        score_abc = Path(output_path).read_text(encoding="utf-8") if Path(output_path).exists() else ""
        await ctx.send_message(MergedScore(score_abc=score_abc, plan=plan, workdir=workdir))

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


class ReviewCollectorExecutor(Executor):
    def __init__(self, id: str = "review_collector"):
        self.id = id

    @handler
    async def process(self, message: Any, ctx: WorkflowContext[MergedScore]) -> None:
        text = message.agent_response.text if hasattr(message, 'agent_response') else str(message)
        await ctx.send_message(MergedScore(score_abc=text, plan={}, workdir=""))


class InjectExecutor(Executor):
    def __init__(self, id: str = "inject"):
        self.id = id

    @handler
    async def process(self, message: MergedScore, ctx: WorkflowContext) -> None:
        from clef_server.tools import write_file, abc_to_midi

        workdir = message.workdir
        score_abc = message.score_abc

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
    if skills_dir is None:
        skills_dir = Path(__file__).resolve().parent.parent.parent.parent / ".claude" / "skills"

    agent_configs: dict[str, AgentConfig] = {
        "clef-composer": AgentConfig(
            prompt_md=Path(".claude/agents/clef-composer.md"),
            model_alias="deepseek", temperature=0.8,
            skills=["melody", "orchestration", "abc"],
            tools=["read_file", "write_file", "validate_abc", "abc_lint"],
        ),
        "clef-harmonist": AgentConfig(
            prompt_md=Path(".claude/agents/clef-harmonist.md"),
            model_alias="deepseek", temperature=0.8,
            skills=["harmony", "abc"],
            tools=["read_file", "write_file", "validate_abc", "abc_lint"],
        ),
        "clef-rhythmist": AgentConfig(
            prompt_md=Path(".claude/agents/clef-rhythmist.md"),
            model_alias="deepseek", temperature=0.7,
            skills=["rhythm", "abc"],
            tools=["read_file", "write_file", "validate_abc", "abc_lint"],
        ),
    }

    # Build the workflow graph
    parse_exec = ParseExecutor(workdir=workdir, id="parse")
    plan_exec = PlanExecutor(id="plan")
    merge_exec = MergeExecutor(id="merge")
    review_exec = ReviewCollectorExecutor(id="review_collector")
    inject_exec = InjectExecutor(id="inject")

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
            # AF not available — create mock executors for testing
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
        WorkflowBuilder(start_executor=parse_exec, name=COMPOSE_WORKFLOW_ID)
        .add_edge(parse_exec, plan_exec)
        .add_fan_out_edges(plan_exec, [
            agent_executors["clef-composer"],
            agent_executors["clef-harmonist"],
            agent_executors["clef-rhythmist"],
        ])
        .add_edge(agent_executors["clef-composer"], extractors["clef-composer"])
        .add_edge(agent_executors["clef-harmonist"], extractors["clef-harmonist"])
        .add_edge(agent_executors["clef-rhythmist"], extractors["clef-rhythmist"])
        .add_fan_in_edges(
            [extractors["clef-composer"], extractors["clef-harmonist"], extractors["clef-rhythmist"]],
            merge_exec,
        )
        .add_edge(merge_exec, review_exec)
        .add_edge(review_exec, inject_exec)
        .build()
    )

    return workflow
