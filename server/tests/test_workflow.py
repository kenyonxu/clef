"""Tests for workflow.py -- compose workflow graph construction."""

from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from clef_server.workflow import (
    MergeExecutor,
    PromptBuilderExecutor,
    InjectExecutor,
    VoiceFragmentExtractor,
    ComposeRequest,
    VoiceFragment,
    MergedScore,
    build_compose_workflow,
    COMPOSE_WORKFLOW_ID,
)


class TestExecutorIDs:
    def test_prompt_builder_executor_id(self):
        assert PromptBuilderExecutor(workdir="/tmp", id="prompt_builder").id == "prompt_builder"

    def test_merge_executor_id(self):
        assert MergeExecutor(workdir="/tmp", id="merge").id == "merge"

    def test_inject_executor_id(self):
        assert InjectExecutor(workdir="/tmp", id="inject").id == "inject"

    def test_voice_fragment_extractor_id(self):
        assert VoiceFragmentExtractor(agent_name="clef-composer", id="extract_clef-composer").id == "extract_clef-composer"


class TestMergeExecutorVoiceLabel:
    def test_extract_v1(self):
        assert MergeExecutor._extract_voice_label("V:1\nK:C\nC D E F|", "agent") == "V:1"

    def test_extract_v2(self):
        assert MergeExecutor._extract_voice_label("V:2\nK:C\nC, E,|", "agent") == "V:2"

    def test_infer_from_agent_name(self):
        assert MergeExecutor._extract_voice_label("no voice header", "clef-composer") == "V:1"
        assert MergeExecutor._extract_voice_label("no voice header", "clef-harmonist") == "V:2"
        assert MergeExecutor._extract_voice_label("no voice header", "clef-rhythmist") == "V:3"
        assert MergeExecutor._extract_voice_label("no voice header", "unknown") == "V:1"


class TestDataClasses:
    def test_compose_request(self):
        req = ComposeRequest(user_prompt="test", workdir="/tmp")
        assert req.user_prompt == "test"
        assert req.plan is None

    def test_voice_fragment(self):
        frag = VoiceFragment(agent_name="clef-composer", abc_content="V:1\nK:C\nC D|")
        assert frag.agent_name == "clef-composer"

    def test_merged_score(self):
        score = MergedScore(score_abc="V:1\nK:C\nC|", plan={}, workdir="/tmp")
        assert score.score_abc.startswith("V:1")


class TestPromptBuilder:
    def test_build_prompt_with_plan(self):
        prompt = PromptBuilderExecutor._build_prompt(
            user_prompt="Write a happy song",
            plan={"title": "Happy", "key": "C"},
            workdir="/tmp/work",
        )
        assert "Happy" in prompt
        assert "Write a happy song" in prompt
        assert "/tmp/work" in prompt

    def test_build_prompt_without_plan_keys(self):
        prompt = PromptBuilderExecutor._build_prompt(
            user_prompt="test",
            plan={},
            workdir="",
        )
        assert "test" in prompt


class TestBuildComposeWorkflow:
    @patch("clef_server.workflow.AgentExecutor")
    @patch("clef_server.workflow.create_agent")
    @patch("clef_server.workflow.WorkflowBuilder")
    def test_returns_workflow(self, MockBuilder, mock_create_agent, MockAE):
        """Verify build_compose_workflow wires the correct graph structure."""
        mock_create_agent.return_value = MagicMock()
        mock_wf = MagicMock()
        MockBuilder.return_value = (
            MagicMock()
            .add_fan_out_edges.return_value
            .add_edge.return_value
            .add_edge.return_value
            .add_edge.return_value
            .add_fan_in_edges.return_value
            .add_edge.return_value
            .build.return_value
        )
        mock_providers = {"deepseek": MagicMock(), "anthropic": MagicMock()}
        wf = build_compose_workflow(
            providers=mock_providers,
            plan={"title": "Test"},
            workdir="/tmp/test",
            skills_dir=Path("/tmp/skills"),
        )
        assert wf is not None
        assert mock_create_agent.call_count == 3
