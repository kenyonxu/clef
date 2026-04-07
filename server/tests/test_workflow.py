"""Tests for workflow.py — compose workflow graph construction."""

from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from clef_server.workflow import (
    MergeExecutor,
    ParseExecutor,
    PlanExecutor,
    InjectExecutor,
    ReviewCollectorExecutor,
    VoiceFragmentExtractor,
    ComposeRequest,
    PlanResult,
    VoiceFragment,
    MergedScore,
    build_compose_workflow,
    COMPOSE_WORKFLOW_ID,
)


class TestExecutorIDs:
    def test_parse_executor_id(self):
        assert ParseExecutor(workdir="/tmp", id="parse").id == "parse"

    def test_plan_executor_id(self):
        assert PlanExecutor(id="plan").id == "plan"

    def test_merge_executor_id(self):
        assert MergeExecutor(id="merge").id == "merge"

    def test_inject_executor_id(self):
        assert InjectExecutor(id="inject").id == "inject"

    def test_review_collector_executor_id(self):
        assert ReviewCollectorExecutor(id="review_collector").id == "review_collector"


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

    def test_plan_result(self):
        result = PlanResult(plan={"key": "C"}, workdir="/tmp")
        assert result.plan["key"] == "C"

    def test_voice_fragment(self):
        frag = VoiceFragment(agent_name="clef-composer", abc_content="V:1\nK:C\nC D|")
        assert frag.agent_name == "clef-composer"

    def test_merged_score(self):
        score = MergedScore(score_abc="V:1\nK:C\nC|", plan={}, workdir="/tmp")
        assert score.score_abc.startswith("V:1")


class TestBuildComposeWorkflow:
    def test_returns_workflow(self):
        mock_providers = {"deepseek": MagicMock(), "anthropic": MagicMock()}
        wf = build_compose_workflow(
            providers=mock_providers,
            plan={"title": "Test"},
            workdir="/tmp/test",
            skills_dir=Path("/tmp/skills"),
        )
        assert wf is not None
