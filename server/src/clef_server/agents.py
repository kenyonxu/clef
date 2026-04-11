"""Agent factory — creates AF Agent instances from config."""

from dataclasses import dataclass
from pathlib import Path

from clef_server.config import AgentConfig
from clef_server.middleware import ClefContextMiddleware
from clef_server.tools import get_tools_for_agent

# AF Agent class — mock for test environments
try:
    from agent_framework import Agent
except ImportError:
    Agent = None


@dataclass
class AgentInstructions:
    """Structured agent instructions with separated layers."""

    system_prompt: str          # Agent markdown (constraints + rules)
    reference_materials: str    # Theory skills (truncated to budget)
    session_context: str        # Plan + score (injected into user message)

    def build_system_message(self) -> str:
        """Combine system_prompt and reference_materials into one system message."""
        if self.reference_materials:
            return (
                f"{self.system_prompt}\n\n"
                f"---\n\n"
                f"# Reference Materials\n\n"
                f"{self.reference_materials}"
            )
        return self.system_prompt

    def build_user_message(self, task: str) -> str:
        """Prepend session context to the user task message."""
        if self.session_context:
            return f"{self.session_context}\n\n---\n\n{task}"
        return task


def build_instructions(
    prompt_md: Path,
    middleware: ClefContextMiddleware,
    plan: dict | None = None,
    score_abc: str | None = None,
    workdir: str = "",
) -> AgentInstructions:
    """Build structured agent instructions with separated layers."""
    system_prompt = prompt_md.read_text(encoding="utf-8")
    reference_materials = middleware.build_skills_section()
    session_context = middleware.build_session_context(
        plan=plan, score_abc=score_abc, workdir=workdir,
    )
    return AgentInstructions(
        system_prompt=system_prompt,
        reference_materials=reference_materials,
        session_context=session_context,
    )


def _build_instructions(
    prompt_md: Path,
    middleware: ClefContextMiddleware,
    plan: dict | None = None,
    score_abc: str | None = None,
    workdir: str = "",
) -> str:
    """Backward-compatible wrapper returning a single system message string."""
    instructions = build_instructions(
        prompt_md=prompt_md,
        middleware=middleware,
        plan=plan,
        score_abc=score_abc,
        workdir=workdir,
    )
    return instructions.build_system_message()


def create_agent(
    name: str,
    config: AgentConfig,
    providers: dict,
    skills_dir: Path,
    plan: dict | None = None,
    score_abc: str | None = None,
    workdir: str = "",
):
    """Create an AF Agent from config.

    Raises:
        ValueError: If provider alias not found.
        FileNotFoundError: If prompt file missing.
    """
    if Agent is None:
        raise RuntimeError("agent-framework-core is not installed")

    client = providers.get(config.model_alias)
    if client is None:
        available = list(providers.keys())
        raise ValueError(f"No provider found for alias '{config.model_alias}'. Available: {available}")

    if not config.prompt_md.exists():
        raise FileNotFoundError(f"Prompt file not found: {config.prompt_md}")

    middleware = ClefContextMiddleware(skills=config.skills, skills_dir=skills_dir)
    instructions = _build_instructions(
        prompt_md=config.prompt_md,
        middleware=middleware,
        plan=plan,
        score_abc=score_abc,
        workdir=workdir,
    )
    tools = get_tools_for_agent(name)

    return Agent(
        client=client,
        name=name,
        instructions=instructions,
        tools=tools,
    )
