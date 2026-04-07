"""Tests for agents.py — Agent factory + middleware."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clef_server.config import AgentConfig
from clef_server.agents import create_agent, _build_instructions
from clef_server.middleware import ClefContextMiddleware


class TestClefContextMiddleware:
    def test_loads_specified_skills(self, skills_dir: Path):
        mw = ClefContextMiddleware(skills=["abc", "melody"], skills_dir=skills_dir)
        assert "theory-abc" in mw._skill_cache
        assert "theory-melody" in mw._skill_cache

    def test_skips_missing_skill_gracefully(self, skills_dir: Path):
        mw = ClefContextMiddleware(skills=["nonexistent_skill"], skills_dir=skills_dir)
        assert mw._skill_cache == {}

    def test_build_context_string(self, skills_dir: Path, sample_plan: dict, sample_abc: str):
        mw = ClefContextMiddleware(skills=["abc"], skills_dir=skills_dir)
        ctx_str = mw.build_context(plan=sample_plan, score_abc=sample_abc, workdir="/tmp/test")
        assert "theory-abc" in ctx_str
        assert "plan.json" in ctx_str


class TestCreateAgent:
    @patch("clef_server.agents.Agent", MagicMock())
    def test_missing_provider_raises(self, agents_dir: Path, skills_dir: Path):
        config = AgentConfig(
            prompt_md=agents_dir / "clef-composer.md",
            model_alias="deepseek",
            skills=[],
            tools=["read_file"],
        )
        with pytest.raises(ValueError, match="No provider found"):
            create_agent("clef-composer", config, {}, skills_dir=skills_dir)

    @patch("clef_server.agents.Agent", MagicMock())
    def test_missing_prompt_file_raises(self, skills_dir: Path):
        config = AgentConfig(
            prompt_md=Path("/nonexistent/clef-composer.md"),
            model_alias="deepseek",
            skills=[],
            tools=["read_file"],
        )
        with pytest.raises(FileNotFoundError, match="Prompt file not found"):
            create_agent("clef-composer", config, {"deepseek": MagicMock()}, skills_dir=skills_dir)


class TestBuildInstructions:
    def test_builds_base_plus_context(self, agents_dir: Path, skills_dir: Path, sample_plan: dict):
        mw = ClefContextMiddleware(skills=["abc"], skills_dir=skills_dir)
        result = _build_instructions(agents_dir / "clef-composer.md", mw, plan=sample_plan)
        assert "Reference Materials" in result
        assert "theory-abc" in result
        assert "plan.json" in result

    def test_builds_base_only_no_context(self, agents_dir: Path, skills_dir: Path):
        mw = ClefContextMiddleware(skills=[], skills_dir=skills_dir)
        result = _build_instructions(agents_dir / "clef-composer.md", mw)
        assert "Reference Materials" not in result
