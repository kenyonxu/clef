"""Agent factory — creates AF Agent instances from config."""

from pathlib import Path

from clef_server.config import AgentConfig
from clef_server.middleware import ClefContextMiddleware
from clef_server.tools import get_tools_for_agent

# AF Agent class — mock for test environments
try:
    from agent_framework import Agent
except ImportError:
    Agent = None


def _build_instructions(
    prompt_md: Path,
    middleware: ClefContextMiddleware,
    plan: dict | None = None,
    score_abc: str | None = None,
    workdir: str = "",
) -> str:
    base = prompt_md.read_text(encoding="utf-8")
    ctx = middleware.build_context(plan=plan, score_abc=score_abc, workdir=workdir)
    if ctx:
        return f"{base}\n\n---\n\n# Reference Materials\n\n{ctx}"
    return base


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
