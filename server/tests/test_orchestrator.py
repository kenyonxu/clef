"""Tests for ComposeOrchestrator -- all phases and navigation."""

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clef_server.orchestrator import (
    PHASE_ORDER,
    ComposeOrchestrator,
    get_session_manager,
)
from clef_server import score_processor, response_parser, validation
from clef_server.sessions import PHASES, SessionManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PLAN_JSON = json.dumps({
    "title": "Test Composition",
    "key": "C",
    "scale": "major",
    "bpm": 120,
    "time_signature": "4/4",
    "form": "ABA",
    "total_bars": 32,
    "sections": [
        {"id": "A", "name": "Verse", "measures": 12},
        {"id": "B", "name": "Chorus", "measures": 8},
        {"id": "A2", "name": "Verse 2", "measures": 12},
    ],
    "orchestration": {
        "melody": {"name": "Piano", "channel": 0, "instrument": "Acoustic Grand Piano", "range": [60, 84], "register": [60, 79]},
        "harmony": {"name": "Piano", "channel": 1, "instrument": "Acoustic Grand Piano", "range": [48, 72], "register": [55, 72]},
        "bass": {"name": "Bass", "channel": 2, "instrument": "Acoustic Bass", "range": [28, 55], "register": [36, 48]},
        "drums": {"name": "Drums", "channel": 9, "instrument": "Standard Kit", "range": [35, 81], "register": [35, 81]},
    },
    "generation_order": ["harmony", "melody"],
    "demo_length_bars": 8,
})


def _make_mock_response(text: str) -> MagicMock:
    """Build a mock ChatResponse with a single assistant message."""
    return MagicMock(
        messages=[MagicMock(contents=[text])],
        finish_reason="stop",
    )


@pytest.fixture
def providers():
    """Mock LLM providers dict with a single 'deepseek' client."""
    mock_client = AsyncMock()
    mock_client.get_response = AsyncMock(
        return_value=_make_mock_response(SAMPLE_PLAN_JSON),
    )
    return {"deepseek": mock_client}


@pytest.fixture
def session(providers, tmp_path):
    """Create a ComposeSession via the global SessionManager."""
    mgr = get_session_manager()
    # Clear previous test sessions to avoid collisions
    mgr._sessions.clear()
    return mgr.create("test prompt", workdir=str(tmp_path))


@pytest.fixture
def orch(session, providers):
    """Create a ComposeOrchestrator wired to the test session."""
    return ComposeOrchestrator(
        session.session_id,
        providers,
        session.workdir,
    )


# ---------------------------------------------------------------------------
# TestOrchestratorInit
# ---------------------------------------------------------------------------

class TestOrchestratorInit:

    def test_create(self, session, providers):
        o = ComposeOrchestrator(session.session_id, providers, session.workdir)
        assert o.session_id == session.session_id
        assert o.providers is providers

    def test_phase_order_constant(self):
        assert PHASE_ORDER[0] == "parse"
        assert len(PHASE_ORDER) == 6

    def test_session_property_refreshes(self, session, providers):
        o = ComposeOrchestrator(session.session_id, providers, session.workdir)
        s1 = o.session
        s2 = o.session
        assert s1.session_id == s2.session_id

    def test_session_property_raises_on_missing(self, providers, tmp_path):
        o = ComposeOrchestrator("nonexistent", providers, str(tmp_path))
        with pytest.raises(RuntimeError, match="not found"):
            _ = o.session


# ---------------------------------------------------------------------------
# TestNextPhase
# ---------------------------------------------------------------------------

class TestNextPhase:

    def test_first_phase(self, orch):
        assert orch._next_phase("parse") == "sample"

    def test_middle_phase(self, orch):
        assert orch._next_phase("create") == "iterate"

    def test_last_phase_returns_none(self, orch):
        assert orch._next_phase("express") is None

    def test_unknown_phase_returns_none(self, orch):
        assert orch._next_phase("nonexistent") is None


# ---------------------------------------------------------------------------
# TestPhaseConfig
# ---------------------------------------------------------------------------

class TestPhaseConfig:

    def test_lookup_parse(self, orch):
        cfg = orch._phase_config("parse")
        assert cfg["id"] == "parse"
        assert cfg["confirm"] is True

    def test_lookup_create(self, orch):
        cfg = orch._phase_config("create")
        assert cfg["confirm"] is False

    def test_lookup_unknown_raises(self, orch):
        with pytest.raises(ValueError, match="Unknown phase"):
            orch._phase_config("nope")


# ---------------------------------------------------------------------------
# TestPhaseParse
# ---------------------------------------------------------------------------

class TestPhaseParse:

    @pytest.mark.asyncio
    async def test_phase_parse_generates_plan(self, orch, session, tmp_path):
        session.set_running()
        with patch("clef_server.config.rename_workdir_with_title", side_effect=lambda w, t: w):
            await orch._phase_parse("Write a boss battle music")

        plan_file = tmp_path / "plan.json"
        assert plan_file.exists()
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        assert plan["key"] == "C"
        assert plan["bpm"] == 120
        assert plan["scale"] == "major"
        assert plan["demo_length_bars"] == 10  # round(32 * 0.3) = 10

    @pytest.mark.asyncio
    async def test_phase_parse_sets_awaiting_confirm(self, orch, session, tmp_path):
        session.set_running()
        with patch("clef_server.config.rename_workdir_with_title", side_effect=lambda w, t: w):
            await orch._phase_parse("Write a boss battle music")

        assert session.status == "awaiting_confirm"
        assert session.confirmation_data is not None
        assert session.confirmation_data["phase"] == "parse"
        assert session.confirmation_data["title"] == "确认音乐规划"
        assert "plan" in session.confirmation_data

    @pytest.mark.asyncio
    async def test_phase_parse_records_history(self, orch, session, tmp_path):
        session.set_running()
        with patch("clef_server.config.rename_workdir_with_title", side_effect=lambda w, t: w):
            await orch._phase_parse("test prompt")

        history = session.phase_history
        assert len(history) == 2  # running + done
        assert history[0]["phase"] == "parse"
        assert history[0]["status"] == "running"
        assert history[1]["phase"] == "parse"
        assert history[1]["status"] == "done"

    @pytest.mark.asyncio
    async def test_phase_parse_strips_code_fence(self, orch, session, tmp_path):
        """LLMs sometimes wrap JSON in ```json ... ``` blocks."""
        session.set_running()
        orch.providers["deepseek"].get_response = AsyncMock(
            return_value=_make_mock_response("```json\n" + SAMPLE_PLAN_JSON + "\n```"),
        )
        with patch("clef_server.config.rename_workdir_with_title", side_effect=lambda w, t: w):
            await orch._phase_parse("test")

        plan_file = tmp_path / "plan.json"
        assert plan_file.exists()
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        assert plan["key"] == "C"

    @pytest.mark.asyncio
    async def test_phase_parse_no_provider_raises(self, session, tmp_path):
        orch = ComposeOrchestrator(session.session_id, {}, str(tmp_path))
        with pytest.raises(RuntimeError, match="No LLM provider"):
            await orch._phase_parse("test")

    @pytest.mark.asyncio
    async def test_start_calls_phase_parse(self, orch, session, tmp_path):
        with patch.object(orch, "_phase_parse", new_callable=AsyncMock) as mock_parse:
            await orch.start("boss battle")
            mock_parse.assert_called_once_with("boss battle")
        assert session.status == "running"  # set_running called first


# ---------------------------------------------------------------------------
# TestResume
# ---------------------------------------------------------------------------

class TestResume:

    @pytest.mark.asyncio
    async def test_resume_from_parse_goes_to_sample(self, orch, session, tmp_path):
        """H1: parse confirm always advances to sample, no feedback loop."""
        session.set_running()
        session.record_phase("parse", "done")
        confirm_data = {"phase": "parse", "title": "确认音乐规划", "plan": {}}
        session.set_awaiting_confirm(confirm_data)

        with patch.object(orch, "_phase_sample", new_callable=AsyncMock) as mock_sample:
            await orch.resume(saved_confirmation_data=confirm_data)
            mock_sample.assert_called_once_with(feedback=None)

    @pytest.mark.asyncio
    async def test_resume_from_parse_ignores_user_feedback(self, orch, session, tmp_path):
        """H1: feedback param is ignored when resuming from parse."""
        session.set_running()
        session.record_phase("parse", "done")
        confirm_data = {"phase": "parse", "plan": {}}
        session.set_awaiting_confirm(confirm_data)

        with patch.object(orch, "_phase_sample", new_callable=AsyncMock) as mock_sample:
            await orch.resume(user_feedback="change the key to Dm", saved_confirmation_data=confirm_data)
            mock_sample.assert_called_once_with(feedback=None)

    @pytest.mark.asyncio
    async def test_resume_not_awaiting_raises(self, orch, session):
        """resume() should raise if no saved confirmation data."""
        session.set_running()
        with pytest.raises(RuntimeError, match="No saved confirmation"):
            await orch.resume(saved_confirmation_data=None)

    @pytest.mark.asyncio
    async def test_resume_revise_from_sample(self, orch, session, tmp_path):
        """Revise action from sample phase should re-run _phase_sample with feedback."""
        session.set_running()
        confirm_data = {"phase": "sample", "title": "试听方向小样"}
        session.set_awaiting_confirm(confirm_data)

        with patch.object(orch, "_phase_sample", new_callable=AsyncMock) as mock_sample:
            await orch.resume(action="revise", user_feedback="more energetic", saved_confirmation_data=confirm_data)
            mock_sample.assert_called_once_with(feedback="more energetic")

    @pytest.mark.asyncio
    async def test_resume_revise_from_review(self, orch, session, tmp_path):
        """Revise action from review phase should call _phase_iterate."""
        session.set_running()
        session.record_phase("iterate", "done")
        confirm_data = {"phase": "review", "title": "试听审核"}
        session.set_awaiting_confirm(confirm_data)

        with patch.object(orch, "_phase_iterate", new_callable=AsyncMock) as mock_iter:
            await orch.resume(action="revise", user_feedback="fix harmony", saved_confirmation_data=confirm_data)
            mock_iter.assert_called_once_with(extra_feedback="fix harmony")


# ---------------------------------------------------------------------------
# TestAdvancePhase
# ---------------------------------------------------------------------------

class TestAdvancePhase:

    @pytest.mark.asyncio
    async def test_advance_to_confirm_phase(self, orch, session, tmp_path):
        """C3: _advance_phase sets awaiting_confirm for confirm phases."""
        session.set_running()

        await orch._advance_phase(
            "parse",
            confirmation_data={
                "phase": "sample",
                "title": "试听方向小样",
            },
        )
        assert session.status == "awaiting_confirm"
        assert session.confirmation_data["phase"] == "sample"

    @pytest.mark.asyncio
    async def test_advance_confirm_defaults_data(self, orch, session, tmp_path):
        """If no confirmation_data provided, default is constructed."""
        session.set_running()
        await orch._advance_phase("parse")
        assert session.confirmation_data is not None
        assert session.confirmation_data["phase"] == "sample"

    @pytest.mark.asyncio
    async def test_advance_to_non_confirm_runs_phase(self, orch, session, tmp_path):
        """Non-confirm phases should auto-run the phase method."""
        session.set_running()
        session.current_phase = "sample"

        with patch.object(orch, "_phase_create", new_callable=AsyncMock) as mock_create:
            await orch._advance_phase("sample")
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_advance_records_running_for_non_confirm(self, orch, session, tmp_path):
        """Non-confirm phases get a 'running' record before execution."""
        session.set_running()
        session.current_phase = "sample"

        async def _stub():
            pass

        with patch.object(orch, "_phase_create", new_callable=AsyncMock, side_effect=_stub):
            await orch._advance_phase("sample")

        phases = [e["phase"] for e in session.phase_history]
        assert "create" in phases

    @pytest.mark.asyncio
    async def test_advance_from_last_phase_completes(self, orch, session, tmp_path):
        """Advancing past 'express' should set session to done."""
        session.set_running()
        # Create output files in workdir root (_collect_outputs uses glob("*"))
        (tmp_path / "final_r1.mid").write_text("fake")

        await orch._advance_phase("express")
        assert session.status == "done"
        assert "final_r1.mid" in session.output_files


# ---------------------------------------------------------------------------
# TestCollectOutputs
# ---------------------------------------------------------------------------

class TestCollectOutputs:

    def test_empty_output_dir(self, orch, tmp_path):
        result = orch._collect_outputs()
        assert result == []

    def test_missing_output_dir(self, orch, tmp_path):
        result = orch._collect_outputs()
        assert result == []

    def test_collects_files(self, orch, tmp_path):
        # _collect_outputs uses glob("*") — only root-level files
        (tmp_path / "final_r1.mid").write_text("data")
        (tmp_path / "score.abc").write_text("notes")

        result = orch._collect_outputs()
        assert len(result) == 2
        assert "final_r1.mid" in result
        assert "score.abc" in result


# ---------------------------------------------------------------------------
# Shared helpers for phase tests (AF not available in test env)
# ---------------------------------------------------------------------------

SAMPLE_PLAN = {
    "title": "Test Piece",
    "key": "C",
    "scale": "major",
    "bpm": 120,
    "time_signature": "4/4",
    "form": "AB",
    "total_bars": 24,
    "sections": [
        {"id": "A", "name": "Section A", "measures": 12},
        {"id": "B", "name": "Section B", "measures": 12},
    ],
    "orchestration": {
        "melody": {"name": "Flute", "channel": 0, "instrument": "flute", "range": "C5-G6", "register": "C5-G6"},
        "harmony": {"name": "Strings", "channel": 1, "instrument": "strings", "range": "G3-E4", "register": "G3-E4"},
    },
    "generation_order": ["harmony", "melody"],
    "demo_length_bars": 8,
}


def _setup_plan(tmp_path, plan=None):
    """Write plan.json and return the plan dict."""
    p = plan or SAMPLE_PLAN
    (tmp_path / "plan.json").write_text(json.dumps(p), encoding="utf-8")
    return p


def _setup_orchestrator(orch, session, tmp_path, plan=None):
    """Common setup: write plan, set session to running state."""
    _setup_plan(tmp_path, plan)
    session.set_running()


# ---------------------------------------------------------------------------
# TestExtractHelpers
# ---------------------------------------------------------------------------

class TestExtractHelpers:

    def test_extract_abc_from_fenced(self, orch):
        text = '```abc\nX:1\nT:Test\nC D E F|\n```'
        result = response_parser.extract_abc(text)
        assert result.startswith("X:1")
        assert "C D E F" in result

    def test_extract_abc_raw(self, orch):
        text = "X:1\nT:Test\nC D E F|"
        result = response_parser.extract_abc(text)
        assert result == text

    def test_extract_abc_fallback(self, orch):
        text = "some raw text without abc header"
        result = response_parser.extract_abc(text)
        assert result == ""  # non-ABC text is now rejected

    def test_extract_abc_rejects_dsml(self, orch):
        text = '<|DSML|function_calls>\n<|DSML|invoke name="write_file">\nX:1\nT:test\n```'
        result = response_parser.extract_abc(text)
        assert result == ""

    def test_extract_abc_raw_header(self, orch):
        text = 'X:1\nT:test\nM:4/4\nK:C\nV:1\nC D E F |'
        result = response_parser.extract_abc(text)
        assert "X:1" in result
        assert "C D E F" in result

    def test_extract_json_from_fenced(self, orch):
        text = '```json\n{"verdict": "pass", "score": 8}\n```'
        result = response_parser.extract_json(text)
        assert result["verdict"] == "pass"
        assert result["score"] == 8

    def test_extract_json_plain(self, orch):
        text = '{"verdict": "revise", "issues": ["bad note"]}'
        result = response_parser.extract_json(text)
        assert result["verdict"] == "revise"

    def test_extract_json_fallback_on_bad_json(self, orch):
        text = "not valid json at all"
        result = response_parser.extract_json(text)
        assert result["verdict"] == "revise"  # bad JSON returns revise verdict (conservative)


# ---------------------------------------------------------------------------
# TestPhaseSample
# ---------------------------------------------------------------------------

class TestPhaseSample:

    @staticmethod
    def _mock_merge(tmp_path):
        """Create a merge_abc mock that actually writes score.abc."""
        def mock_merge(plan, fragments, output):
            Path(output).write_text("X:1\nT:Merged\nM:4/4\nK:C\nV:1\nC D E F|G A B c|\n", encoding="utf-8")
            return {"output": output}
        return mock_merge

    @pytest.mark.asyncio
    async def test_phase_sample_sets_confirm(self, session, providers, tmp_path):
        """Phase sample should end with awaiting_confirm status."""
        _setup_orchestrator(
            ComposeOrchestrator(session.session_id, providers, str(tmp_path)),
            session, tmp_path,
        )
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))

        async def mock_run(agent_name, message, **kw):
            return f'X:1\nT:Sample\nM:4/4\nK:C\nV:1\nC D E F|'

        orch._run_agent = mock_run

        with patch("clef_server.tools.merge_abc", side_effect=self._mock_merge(tmp_path)), \
             patch("clef_server.tools.abc_to_midi", return_value={"output": "sample_r1.mid"}):
            await orch._phase_sample()

        assert session.status == "awaiting_confirm"
        assert session.confirmation_data is not None
        assert session.confirmation_data["phase"] == "sample"
        assert "sample_file" in session.confirmation_data

    @pytest.mark.asyncio
    async def test_phase_sample_records_history(self, session, providers, tmp_path):
        """Phase sample should record running + done in phase_history."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)

        async def mock_run(agent_name, message, **kw):
            return "X:1\nT:Test\nM:4/4\nK:C\nC D E F|"

        orch._run_agent = mock_run

        with patch("clef_server.tools.merge_abc", side_effect=self._mock_merge(tmp_path)), \
             patch("clef_server.tools.abc_to_midi", return_value={"output": "sample_r1.mid"}):
            await orch._phase_sample()

        phases = [e for e in session.phase_history if e["phase"] == "sample"]
        assert len(phases) == 2
        assert phases[0]["status"] == "running"
        assert phases[1]["status"] == "done"

    @pytest.mark.asyncio
    async def test_phase_sample_h2_sets_current_phase(self, session, providers, tmp_path):
        """H2: _phase_sample must set session.current_phase = 'sample'."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)

        async def mock_run(agent_name, message, **kw):
            return "X:1\nM:4/4\nK:C\nC D E F|"

        orch._run_agent = mock_run

        with patch("clef_server.tools.merge_abc", side_effect=self._mock_merge(tmp_path)), \
             patch("clef_server.tools.abc_to_midi", return_value={"output": "sample_r1.mid"}):
            await orch._phase_sample()

        assert session.current_phase == "sample"


# ---------------------------------------------------------------------------
# TestPhaseCreate
# ---------------------------------------------------------------------------

class TestPhaseCreate:

    @pytest.mark.asyncio
    async def test_phase_create_produces_files(self, session, providers, tmp_path):
        """Phase create should produce score.abc and base_r1.mid (via tool calls)."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        session.current_phase = "create"

        async def mock_run(agent_name, message, **kw):
            return "X:1\nT:Full\nM:4/4\nK:C\nC D E F|G A B c|"

        orch._run_agent = mock_run

        # Patch merge_abc to actually write score.abc
        def mock_merge(plan, fragments, output):
            Path(output).write_text("X:1\nMerged\n", encoding="utf-8")
            return {"output": output}

        with patch("clef_server.tools.merge_abc", side_effect=mock_merge), \
             patch("clef_server.tools.validate_abc", return_value={"report": {"is_valid": True}}), \
             patch("clef_server.tools.abc_to_midi", return_value={"output": "base_r1.mid"}) as mock_midi, \
             patch.object(orch, "_advance_phase", new_callable=AsyncMock):
            await orch._phase_create()

        # Verify abc_to_midi was called
        mock_midi.assert_called_once()
        assert (tmp_path / "score.abc").exists()

    @pytest.mark.asyncio
    async def test_phase_create_advances_phase(self, session, providers, tmp_path):
        """Phase create should call _advance_phase('create') when done."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        session.current_phase = "create"

        async def mock_run(agent_name, message, **kw):
            return "X:1\nM:4/4\nK:C\nC D E F|"

        orch._run_agent = mock_run

        def mock_merge(plan, fragments, output):
            Path(output).write_text("X:1\nV:1\nC D E F|\n", encoding="utf-8")
            return {"output": output}

        with patch("clef_server.tools.merge_abc", side_effect=mock_merge), \
             patch("clef_server.tools.validate_abc", return_value={"report": {"is_valid": True}}), \
             patch("clef_server.tools.abc_to_midi", return_value={"output": "base_r1.mid"}), \
             patch.object(orch, "_advance_phase", new_callable=AsyncMock) as mock_advance:
            await orch._phase_create()
            mock_advance.assert_called_once_with("create")


# ---------------------------------------------------------------------------
# TestPhaseIterate
# ---------------------------------------------------------------------------

class TestPhaseIterate:

    @pytest.mark.asyncio
    async def test_phase_iterate_updates_count(self, session, providers, tmp_path):
        """Phase iterate should increment session.iteration_count."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        (tmp_path / "score.abc").write_text("X:1\nM:4/4\nK:C\nC D E F|\n", encoding="utf-8")
        session.current_phase = "iterate"

        call_count = {"n": 0}

        async def mock_run(agent_name, message, **kw):
            call_count["n"] += 1
            # First call is reviewer, second is leader — leader says done
            if call_count["n"] == 2:
                return '{"iteration_complete": true, "tasks": []}'
            return '{"verdict": "pass", "score": 7, "issues": []}'

        orch._run_agent = mock_run

        with patch("clef_server.tools.validate_abc", return_value={"report": {"is_valid": True}}), \
             patch.object(orch, "_advance_phase", new_callable=AsyncMock):
            await orch._phase_iterate()

        assert session.iteration_count >= 1

    @pytest.mark.asyncio
    async def test_phase_iterate_c6_sets_confirmation_data(self, session, providers, tmp_path):
        """C6: _phase_iterate should set confirmation_data with review + iteration_count."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        (tmp_path / "score.abc").write_text("X:1\nM:4/4\nK:C\nC D E F|\n", encoding="utf-8")
        session.current_phase = "iterate"

        call_count = {"n": 0}

        async def mock_run(agent_name, message, **kw):
            call_count["n"] += 1
            if call_count["n"] == 2:
                return '{"iteration_complete": true, "tasks": []}'
            return '{"verdict": "pass", "score": 8, "issues": []}'

        orch._run_agent = mock_run

        with patch("clef_server.tools.validate_abc", return_value={"report": {"is_valid": True}}), \
             patch.object(orch, "_advance_phase", new_callable=AsyncMock) as mock_advance:
            await orch._phase_iterate()
            # Check that _advance_phase was called with confirmation_data
            args, kwargs = mock_advance.call_args
            assert args[0] == "iterate"
            assert "confirmation_data" in kwargs
            data = kwargs["confirmation_data"]
            assert data["phase"] == "review"
            assert "review" in data
            assert "iteration_count" in data

    @pytest.mark.asyncio
    async def test_phase_iterate_h7_no_empty_merge(self, session, providers, tmp_path):
        """H7: iteration should NOT call merge_abc with empty fragments."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        (tmp_path / "score.abc").write_text("X:1\nM:4/4\nK:C\nC D E F|\n", encoding="utf-8")
        session.current_phase = "iterate"

        async def mock_run(agent_name, message, **kw):
            # Return iteration_complete immediately
            return '{"iteration_complete": true, "tasks": []}'

        orch._run_agent = mock_run

        with patch("clef_server.tools.validate_abc", return_value={"report": {"is_valid": True}}), \
             patch("clef_server.tools.merge_abc") as mock_merge, \
             patch.object(orch, "_advance_phase", new_callable=AsyncMock):
            await orch._phase_iterate()
            # merge_abc should NOT be called during iteration
            mock_merge.assert_not_called()

    @pytest.mark.asyncio
    async def test_phase_iterate_respects_max_rounds(self, session, providers, tmp_path):
        """Iteration should stop after MAX_ITERATION_ROUNDS."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        (tmp_path / "score.abc").write_text("X:1\nM:4/4\nK:C\nC D E F|\n", encoding="utf-8")
        session.current_phase = "iterate"

        call_count = {"n": 0}

        async def mock_run(agent_name, message, **kw):
            call_count["n"] += 1
            # Leader always returns tasks (never iteration_complete)
            if call_count["n"] % 2 == 0:
                return '{"iteration_complete": false, "tasks": [{"agent": "clef-composer", "voice": "melody", "depends_on": "", "instruction": "fix melody"}]}'
            return '{"verdict": "revise", "score": 3, "issues": ["bad"]}'

        orch._run_agent = mock_run

        with patch("clef_server.tools.validate_abc", return_value={"report": {"is_valid": True}}), \
             patch("clef_server.tools.merge_abc", return_value={"output": "score.abc"}), \
             patch.object(orch, "_advance_phase", new_callable=AsyncMock):
            await orch._phase_iterate()

        assert session.iteration_count <= orch.MAX_ITERATION_ROUNDS


# ---------------------------------------------------------------------------
# TestPhaseExpress
# ---------------------------------------------------------------------------

class TestPhaseExpress:

    @pytest.mark.asyncio
    async def test_phase_express_sets_done(self, session, providers, tmp_path):
        """Phase express should set session to done status."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        (tmp_path / "base_r1.mid").write_bytes(b"MThd\x00\x00\x00\x06")
        session.current_phase = "express"

        async def mock_run(agent_name, message, **kw):
            return '{"cc7_volume": [{"beat": 1, "value": 100}]}'

        orch._run_agent = mock_run

        with patch("clef_server.tools.inject_expression", return_value={"output": "output/final_r1.mid"}) as mock_inject:
            await orch._phase_express()

        assert session.status == "done"
        mock_inject.assert_called_once()

    @pytest.mark.asyncio
    async def test_phase_express_creates_output_dir(self, session, providers, tmp_path):
        """Phase express should produce output MIDI file."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        (tmp_path / "base_r1.mid").write_bytes(b"MThd\x00\x00\x00\x06")
        session.current_phase = "express"

        async def mock_run(agent_name, message, **kw):
            return "{}"

        orch._run_agent = mock_run

        with patch("clef_server.tools.inject_expression", return_value={"output": str(tmp_path / "final_r1.mid")}):
            await orch._phase_express()

        assert session.status == "done"

    @pytest.mark.asyncio
    async def test_phase_express_c4_no_binary_read(self, session, providers, tmp_path):
        """C4: _phase_express should not read MIDI as text (only check exists)."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        (tmp_path / "base_r1.mid").write_bytes(b"MThd\x00\x00\x00\x06")
        session.current_phase = "express"

        # The MIDI file has 6 bytes. If read as text it would be very short.
        # Express should not fail because of this.
        async def mock_run(agent_name, message, **kw):
            return "{}"

        orch._run_agent = mock_run

        with patch("clef_server.tools.inject_expression", return_value={"output": "output/final_r1.mid"}):
            await orch._phase_express()

        assert session.status == "done"

    @pytest.mark.asyncio
    async def test_phase_express_missing_base_mid(self, session, providers, tmp_path):
        """C4: If base_r*.mid missing, express should gracefully complete."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        # Do NOT create base_r*.mid
        session.current_phase = "express"

        with patch("clef_server.tools.inject_expression") as mock_inject:
            await orch._phase_express()

        # Should complete without calling inject_expression
        mock_inject.assert_not_called()
        assert session.status == "done"


# ---------------------------------------------------------------------------
# TestDedupCachePathNormalization
# ---------------------------------------------------------------------------


class TestDedupCachePathNormalization:
    """Verify that plan_path normalization causes DEDUP cache hits across
    relative and absolute path variations."""

    @pytest.fixture
    def orch(self, tmp_path, providers):
        """Create orchestrator with abc_lint mocked to return a deterministic result."""
        (tmp_path / "plan.json").write_text('{"key":"C"}', encoding="utf-8")
        orch = ComposeOrchestrator("test-session", providers, str(tmp_path))
        return orch

    def _mock_abc_lint(self):
        """Return a mock abc_lint that accepts any kwargs."""
        def mock_lint(abc_content, plan_path="", **_kw):
            return {"ok": True, "issues": []}
        # Wrap as a FunctionTool-like object
        mock_lint.func = mock_lint
        return mock_lint

    def test_relative_then_absolute_plan_path_hits_cache(self, orch, tmp_path):
        """abc_lint with 'plan.json' then '<abs>/plan.json' should DEDUP hit."""
        mock_lint = self._mock_abc_lint()
        executor = orch._make_tool_executor("clef-composer")
        abs_plan = str((tmp_path / "plan.json").resolve())

        abc_content = "X:1\nM:4/4\nK:C\nC D E F|"

        # Call 1: relative plan_path → real execution (mocked)
        call1 = {"name": "abc_lint", "arguments": json.dumps({
            "abc_content": abc_content, "plan_path": "plan.json",
        })}
        with patch.dict("clef_server.tools.TOOLS_REGISTRY", {"abc_lint": mock_lint}):
            result1 = executor(call1)
        assert result1.get("ok") is True
        assert "_dedup" not in result1

        # Call 2: absolute plan_path → DEDUP cache hit
        call2 = {"name": "abc_lint", "arguments": json.dumps({
            "abc_content": abc_content, "plan_path": abs_plan,
        })}
        with patch.dict("clef_server.tools.TOOLS_REGISTRY", {"abc_lint": mock_lint}):
            result2 = executor(call2)
        assert result2.get("_dedup") is True, (
            f"Expected DEDUP cache hit for absolute plan_path, got: {result2}"
        )

    def test_absolute_then_relative_plan_path_hits_cache(self, orch, tmp_path):
        """Reverse order: absolute first, relative second should also DEDUP hit."""
        mock_lint = self._mock_abc_lint()
        executor = orch._make_tool_executor("clef-composer")
        abs_plan = str((tmp_path / "plan.json").resolve())
        abc_content = "X:1\nM:4/4\nK:C\nG A B c|"

        call1 = {"name": "abc_lint", "arguments": json.dumps({
            "abc_content": abc_content, "plan_path": abs_plan,
        })}
        with patch.dict("clef_server.tools.TOOLS_REGISTRY", {"abc_lint": mock_lint}):
            result1 = executor(call1)
        assert "_dedup" not in result1

        call2 = {"name": "abc_lint", "arguments": json.dumps({
            "abc_content": abc_content, "plan_path": "plan.json",
        })}
        with patch.dict("clef_server.tools.TOOLS_REGISTRY", {"abc_lint": mock_lint}):
            result2 = executor(call2)
        assert result2.get("_dedup") is True

    def test_different_content_does_not_hit_cache(self, orch, tmp_path):
        """Different abc_content should NOT produce a DEDUP cache hit."""
        mock_lint = self._mock_abc_lint()
        executor = orch._make_tool_executor("clef-composer")

        call1 = {"name": "abc_lint", "arguments": json.dumps({
            "abc_content": "X:1\nM:4/4\nK:C\nC D E F|", "plan_path": "plan.json",
        })}
        call2 = {"name": "abc_lint", "arguments": json.dumps({
            "abc_content": "X:1\nM:4/4\nK:G\nG A B c|", "plan_path": "plan.json",
        })}
        with patch.dict("clef_server.tools.TOOLS_REGISTRY", {"abc_lint": mock_lint}):
            result1 = executor(call1)
            result2 = executor(call2)
        assert "_dedup" not in result1
        assert result2.get("_dedup") is not True


# ---------------------------------------------------------------------------
# TestResumeReview
# ---------------------------------------------------------------------------

class TestResumeReview:

    @pytest.mark.asyncio
    async def test_resume_review_with_feedback_triggers_iterate(self, session, providers, tmp_path):
        """Resume from review with feedback should call _phase_iterate."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        session.set_running()
        session.record_phase("iterate", "done")
        confirm_data = {"phase": "review", "title": "试听审核"}
        session.set_awaiting_confirm(confirm_data)

        with patch.object(orch, "_phase_iterate", new_callable=AsyncMock) as mock_iter:
            await orch.resume(user_feedback="make it more energetic", saved_confirmation_data=confirm_data)
            mock_iter.assert_called_once_with(extra_feedback="make it more energetic")

    @pytest.mark.asyncio
    async def test_resume_review_no_feedback_advances_to_express(self, session, providers, tmp_path):
        """Resume from review without feedback should call _phase_express."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        session.set_running()
        session.record_phase("iterate", "done")
        confirm_data = {"phase": "review", "title": "试听审核"}
        session.set_awaiting_confirm(confirm_data)

        with patch.object(orch, "_phase_express", new_callable=AsyncMock) as mock_expr:
            await orch.resume(saved_confirmation_data=confirm_data)
            mock_expr.assert_called_once()


# ---------------------------------------------------------------------------
# TestResolveAgentName
# ---------------------------------------------------------------------------

class TestResolveAgentName:
    """Test three-layer agent name resolution."""

    @pytest.fixture
    def orch(self):
        providers = {"test": MagicMock()}
        return ComposeOrchestrator(
            session_id="test-resolve",
            providers=providers,
            workdir="/tmp/test",
        )

    def test_exact_match(self, orch):
        assert orch._resolve_agent_name("clef-composer") == "clef-composer"

    def test_case_insensitive(self, orch):
        assert orch._resolve_agent_name("clef-Composer") == "clef-composer"
        assert orch._resolve_agent_name("CLEF-COMPOSER") == "clef-composer"

    def test_alias_melodist(self, orch):
        assert orch._resolve_agent_name("clef-melodist") == "clef-composer"
        assert orch._resolve_agent_name("melodist") == "clef-composer"

    def test_alias_bassist(self, orch):
        assert orch._resolve_agent_name("clef-bassist") == "clef-rhythmist"
        assert orch._resolve_agent_name("drummer") == "clef-rhythmist"
        assert orch._resolve_agent_name("percussionist") == "clef-rhythmist"

    def test_voice_routing(self, orch):
        assert orch._resolve_agent_name("clef-melody-writer", voice="melody") == "clef-composer"
        assert orch._resolve_agent_name("totally-wrong-name", voice="harmony") == "clef-harmonist"
        assert orch._resolve_agent_name("unknown", voice="rhythm") == "clef-rhythmist"

    def test_no_match_returns_none(self, orch):
        assert orch._resolve_agent_name("totally-wrong-name") is None
        assert orch._resolve_agent_name("totally-wrong", voice="unknown_voice") is None

    def test_bare_name_without_prefix(self, orch):
        assert orch._resolve_agent_name("composer") == "clef-composer"
        assert orch._resolve_agent_name("harmonist") == "clef-harmonist"
        assert orch._resolve_agent_name("rhythmist") == "clef-rhythmist"


# ---------------------------------------------------------------------------
# TestExtractJsonConservativeFallback
# ---------------------------------------------------------------------------

class TestExtractJsonConservativeFallback:
    """_extract_json should return 'revise' verdict on parse failure, not 'pass'."""

    @pytest.fixture
    def orch(self):
        providers = {"test": MagicMock()}
        return ComposeOrchestrator(
            session_id="test-json", providers=providers, workdir="/tmp/test",
        )

    def test_invalid_json_returns_revise(self, orch):
        result = response_parser.extract_json("this is not json at all")
        assert result["verdict"] == "revise"

    def test_valid_json_pass_verdict_preserved(self, orch):
        result = response_parser.extract_json('{"verdict": "pass", "overall_score": 8}')
        assert result["verdict"] == "pass"
        assert result["overall_score"] == 8

    def test_valid_json_revise_verdict_preserved(self, orch):
        result = response_parser.extract_json('{"verdict": "revise", "overall_score": 4}')
        assert result["verdict"] == "revise"


# ---------------------------------------------------------------------------
# TestStripToolMarkers
# ---------------------------------------------------------------------------

class TestStripToolMarkers:
    """Test DSML marker stripping for content recovery."""

    @pytest.fixture
    def orch(self):
        providers = {"test": MagicMock()}
        return ComposeOrchestrator(
            session_id="test-strip", providers=providers, workdir="/tmp/test",
        )

    def test_no_markers_leaves_text_intact(self, orch):
        text = 'V:1\nC D E F | G A B c |'
        assert response_parser.strip_tool_markers(text) == text

    def test_removes_dsml_markers(self, orch):
        text = 'V:1\nC D E F | <function_calls>some tool stuff</function_calls>'
        stripped = response_parser.strip_tool_markers(text)
        assert "<function_calls>" not in stripped
        assert "V:1" in stripped
        assert "C D E F" in stripped

    def test_removes_invoke_tags(self, orch):
        text = 'Result:\nV:1\nC D E |\n<invoke name="write_file">\nsome params\n</invoke>'
        stripped = response_parser.strip_tool_markers(text)
        assert "<invoke" not in stripped
        assert "V:1" in stripped


class TestPerVoiceTruncation:
    """Tests for per-voice truncation in iterate phase."""

    def test_truncate_score_per_voice_4_voices(self):
        """Per-voice truncation preserves all 4 voices, truncating each independently."""
        abc = (
            "X:1\nT:Test\nM:4/4\nL:1/4\n"
            "V:1\nC D E F|G A B c|c B A G|F E D C|C D E F|G A B c|\n"
            "V:2\n[C E G]| [D F A]| [E G B]| [C E G]| [D F A]| [E G B]|\n"
            "V:3\nC,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|\n"
            "V:4\n^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|\n"
        )
        result = score_processor.truncate_score_per_voice(abc, 3)
        # All 4 voices should still be present
        assert "V:1" in result
        assert "V:2" in result
        assert "V:3" in result
        assert "V:4" in result
        # Each voice should have at most 3 bar lines
        for vl in ["V:1", "V:2", "V:3", "V:4"]:
            blocks = score_processor.parse_voice_blocks(result)
            if vl in blocks:
                bars = score_processor.count_bars(blocks[vl])
                assert bars <= 3, f"{vl} has {bars} bars, expected <= 3"

    def test_truncate_score_per_voice_no_over_truncate(self):
        """Score with correct bar count per voice is not modified."""
        abc = (
            "X:1\nT:Test\nM:4/4\nL:1/4\n"
            "V:1\nC D E F|G A B c|c B A G|\n"
            "V:2\n[C E G]| [D F A]| [E G B]|\n"
        )
        result = score_processor.truncate_score_per_voice(abc, 3)
        assert "V:1" in result
        assert "V:2" in result
        blocks = score_processor.parse_voice_blocks(result)
        assert score_processor.count_bars(blocks.get("V:1", "")) == 3

    def test_old_global_truncate_destroys_voices(self):
        """Document the OLD bug: _truncate_to_bars on merged 4-voice score destroys later voices."""
        abc = (
            "X:1\nT:Test\nM:4/4\nL:1/4\n"
            "V:1\nC D E F|G A B c|c B A G|F E D C|C D E F|G A B c|c B A G|F E D C|C D E F|G A B c|\n"
            "V:2\n[C E G]| [D F A]| [E G B]| [C E G]| [D F A]| [E G B]| [C E G]| [D F A]| [E G B]| [C E G]|\n"
            "V:3\nC,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|C,2 G,2|D,2 A,2|\n"
            "V:4\n^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|^D ^A ^D ^A|\n"
        )
        # OLD behavior: global truncation with target=10 cuts across all 40 bars, destroying V:3/V:4
        result_old = score_processor.truncate_to_bars(abc, 10)
        assert "V:3" not in result_old or "V:4" not in result_old
        # NEW behavior: per-voice truncation preserves all voices
        result_new = score_processor.truncate_score_per_voice(abc, 10)
        assert "V:1" in result_new
        assert "V:2" in result_new
        assert "V:3" in result_new
        assert "V:4" in result_new


# ---------------------------------------------------------------------------
# TestExpressPlanValidation
# ---------------------------------------------------------------------------

class TestExpressPlanValidation:
    """Tests for expression plan format validation."""

    @pytest.mark.asyncio
    async def test_express_skips_invalid_plan(self):
        """_phase_express should skip when expression_plan has no valid keys."""
        mgr = get_session_manager()
        mgr._sessions.clear()
        tmp_path = Path(tempfile.mkdtemp())

        plan = {"key": "C", "scale": "major", "bpm": 120, "form": "ABA", "total_bars": 8}
        (tmp_path / "plan.json").write_text(json.dumps(plan))
        (tmp_path / "base_r1.mid").write_bytes(
            b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x00\x60"
        )

        session = mgr.create("test", workdir=str(tmp_path))
        session.set_running()
        session.iteration_count = 1

        providers = {"test": AsyncMock()}
        orchestrator = ComposeOrchestrator(session.session_id, providers, str(tmp_path))

        # Mock _run_agent to return invalid JSON
        invalid_response = '{"verdict": "revise"}'
        orchestrator._run_agent = AsyncMock(return_value=invalid_response)

        await orchestrator._phase_express()

        # Should NOT have created expression_plan.json
        assert not (tmp_path / "expression_plan.json").exists()
        # Session should be marked done (early exit)
        assert session.status == "done"

        # Cleanup
        shutil.rmtree(tmp_path, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_express_saves_valid_plan(self):
        """_phase_express should save when plan has valid keys."""
        mgr = get_session_manager()
        mgr._sessions.clear()
        tmp_path = Path(tempfile.mkdtemp())

        plan = {"key": "C", "scale": "major", "bpm": 120, "form": "ABA", "total_bars": 8}
        (tmp_path / "plan.json").write_text(json.dumps(plan))
        (tmp_path / "base_r1.mid").write_bytes(
            b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x00\x60"
        )

        session = mgr.create("test", workdir=str(tmp_path))
        session.set_running()
        session.iteration_count = 1

        providers = {"test": AsyncMock()}
        orchestrator = ComposeOrchestrator(session.session_id, providers, str(tmp_path))

        valid_response = '{"cc7_volume": [{"beat": 0, "value": 80}]}'
        orchestrator._run_agent = AsyncMock(return_value=valid_response)

        with patch("clef_server.tools.inject_expression", return_value={"ok": True}):
            await orchestrator._phase_express()

        assert (tmp_path / "expression_plan.json").exists()
        saved = json.loads((tmp_path / "expression_plan.json").read_text())
        assert "cc7_volume" in saved

        # Cleanup
        shutil.rmtree(tmp_path, ignore_errors=True)


class TestReviewerValidationContext:
    """Tests for passing validation failures to reviewer."""

    @pytest.mark.asyncio
    async def test_call_reviewer_includes_validation_failures(self):
        """_call_reviewer message should include validation failure details."""
        orchestrator = ComposeOrchestrator.__new__(ComposeOrchestrator)
        tmp_path = Path(tempfile.mkdtemp())

        plan = {"key": "C", "scale": "major", "bpm": 120, "form": "ABA", "total_bars": 8}
        score_abc = "X:1\nT:Test\nM:4/4\nV:1\nC D E F|G A B c|\n"
        (tmp_path / "score.abc").write_text(score_abc)

        orchestrator.workdir = str(tmp_path)

        captured_message = None

        async def mock_run_agent(agent_name, message, **kwargs):
            nonlocal captured_message
            captured_message = message
            return '{"dimensions":{"melody":{"score":5,"issues":[]}},"overall_score":5,"verdict":"revise","summary":"test"}'

        orchestrator._run_agent = mock_run_agent

        failures = [
            {"category": "measure_duration", "voice": "V:1", "message": "bar 3 has 5 beats"},
            {"category": "voice_alignment", "voice": "global", "message": "voices misaligned"},
        ]

        await orchestrator._call_reviewer(plan, validation_failures=failures)

        assert captured_message is not None
        assert "VALIDATION REPORT" in captured_message
        assert "FAIL-level issue" in captured_message
        assert "measure_duration" in captured_message

        shutil.rmtree(tmp_path, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_call_reviewer_no_failures_no_extra_text(self):
        """_call_reviewer without failures should not include validation section."""
        orchestrator = ComposeOrchestrator.__new__(ComposeOrchestrator)
        tmp_path = Path(tempfile.mkdtemp())

        plan = {"key": "C", "scale": "major", "bpm": 120, "form": "ABA"}
        (tmp_path / "score.abc").write_text("X:1\nT:Test\nV:1\nC D E F|\n")

        orchestrator.workdir = str(tmp_path)

        captured_message = None

        async def mock_run_agent(agent_name, message, **kwargs):
            nonlocal captured_message
            captured_message = message
            return '{"dimensions":{"melody":{"score":8,"issues":[]}},"overall_score":8,"verdict":"pass","summary":"ok"}'

        orchestrator._run_agent = mock_run_agent

        await orchestrator._call_reviewer(plan, validation_failures=None)

        # "VALIDATION REPORT" appears in SCORING RULES text, so check for the
        # actual failure-block header which only appears when failures are present
        assert "VALIDATION REPORT (automated checks)" not in captured_message

        shutil.rmtree(tmp_path, ignore_errors=True)


class TestReviewerScoringConstraints:
    """Tests for FAIL-penalty scoring instructions in reviewer prompt."""

    @pytest.mark.asyncio
    async def test_reviewer_prompt_contains_scoring_rules(self):
        """Reviewer prompt should include FAIL-penalty scoring rules."""
        orchestrator = ComposeOrchestrator.__new__(ComposeOrchestrator)
        tmp_path = Path(tempfile.mkdtemp())

        plan = {"key": "C", "scale": "major", "bpm": 120, "form": "ABA"}
        (tmp_path / "score.abc").write_text("X:1\nT:Test\nV:1\nC D E F|\n")

        orchestrator.workdir = str(tmp_path)

        captured_message = None

        async def mock_run_agent(agent_name, message, **kwargs):
            nonlocal captured_message
            captured_message = message
            return '{"dimensions":{"melody":{"score":5,"issues":[]}},"overall_score":5,"verdict":"revise","summary":"test"}'

        orchestrator._run_agent = mock_run_agent

        await orchestrator._call_reviewer(plan)

        assert "SCORING RULES" in captured_message
        assert "FAIL-level issues" in captured_message

        shutil.rmtree(tmp_path, ignore_errors=True)


class TestIterateEarlyStop:
    """Tests for early-stop when validation fail_count stagnates."""

    @pytest.mark.asyncio
    async def test_iterate_stops_on_stagnation(self):
        """Iteration should stop after 2 rounds with no fail_count improvement."""
        mgr = get_session_manager()
        mgr._sessions.clear()
        tmp_path = Path(tempfile.mkdtemp())

        plan = {
            "key": "C", "scale": "major", "bpm": 120, "form": "ABA",
            "total_bars": 8,
            "sections": [
                {"name": "A", "bars": 4, "energy_level": 5},
                {"name": "B", "bars": 4, "energy_level": 7},
            ],
            "orchestration": [
                {"voice": "V:1", "label": "melody", "instrument": "Piano"},
            ],
        }
        (tmp_path / "plan.json").write_text(json.dumps(plan))
        (tmp_path / "score.abc").write_text("X:1\nT:Test\nM:4/4\nV:1\nC D E F|G A B c|c B A G|F E D C|\n")

        session = mgr.create("test", workdir=str(tmp_path))
        session.set_running()
        session.iteration_count = 0

        providers = {"test": AsyncMock()}
        orchestrator = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        orchestrator.max_iteration_rounds = 5
        orchestrator._stagnation_count = 0
        orchestrator._prev_iteration_fail_count = None
        orchestrator._iteration_history = []
        orchestrator._validation_failures = []

        orchestrator._call_reviewer = AsyncMock(return_value={
            "verdict": "revise",
            "scores": {"melody": 5},
            "issues": ["bad melody"],
        })

        call_count = 0
        async def mock_leader(plan, review, **kwargs):
            nonlocal call_count
            call_count += 1
            return {
                "tasks": [{"agent": "clef-composer", "voice": "melody", "instruction": "fix"}],
                "iteration_complete": False,
            }

        orchestrator._call_leader = mock_leader
        orchestrator._run_agent = AsyncMock(return_value="C D E F|G A B c|c B A G|F E D C|")
        orchestrator._agent_defs = {"clef-composer": {}}
        orchestrator.VOICE_MAP = {"melody": "V:1"}
        orchestrator.inter_agent_delay = 0

        # Always return 10 failures (stagnant)
        stagnant_failures = [{"category": "duration", "voice": "V:1", "message": "measure too long", "severity": "FAIL"}] * 10

        with patch("clef_server.tools.merge_abc", return_value={"ok": True}):
            with patch("clef_server.tools.abc_to_midi", return_value={"ok": True}):
                with patch("clef_server.orchestrator.response_parser.extract_abc", side_effect=lambda x: x):
                    with patch("clef_server.orchestrator.score_processor.inject_midi_programs"):
                        with patch("clef_server.orchestrator.score_processor.store_fragment"):
                            with patch("clef_server.orchestrator.validation.run_validation", return_value=stagnant_failures):
                                await orchestrator._phase_iterate()

        # Should have stopped before reaching 5 rounds due to stagnation
        # Round 1: stagnation=0 (no prev), round 2: stagnation=1, round 3: stagnation=2 -> break
        assert orchestrator.session.iteration_count < 5, \
            f"Expected early stop but ran {orchestrator.session.iteration_count} rounds"
        assert orchestrator.session.iteration_count == 3, \
            f"Expected 3 rounds (stagnation after 2), got {orchestrator.session.iteration_count}"

        shutil.rmtree(tmp_path, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_iterate_continues_on_improvement(self):
        """Iteration should continue when fail_count improves."""
        mgr = get_session_manager()
        mgr._sessions.clear()
        tmp_path = Path(tempfile.mkdtemp())

        plan = {
            "key": "C", "scale": "major", "bpm": 120, "form": "ABA",
            "total_bars": 8,
            "sections": [{"name": "A", "bars": 4}, {"name": "B", "bars": 4}],
            "orchestration": [{"voice": "V:1", "label": "melody", "instrument": "Piano"}],
        }
        (tmp_path / "plan.json").write_text(json.dumps(plan))
        (tmp_path / "score.abc").write_text("X:1\nT:Test\nM:4/4\nV:1\nC D E F|G A B c|c B A G|F E D C|\n")

        session = mgr.create("test", workdir=str(tmp_path))
        session.set_running()
        session.iteration_count = 0

        providers = {"test": AsyncMock()}
        orchestrator = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        orchestrator.max_iteration_rounds = 3
        orchestrator._stagnation_count = 0
        orchestrator._prev_iteration_fail_count = None
        orchestrator._iteration_history = []
        orchestrator._validation_failures = []

        orchestrator._call_reviewer = AsyncMock(return_value={
            "verdict": "revise", "scores": {"melody": 5}, "issues": [],
        })

        orchestrator._call_leader = AsyncMock(return_value={
            "tasks": [{"agent": "clef-composer", "voice": "melody", "instruction": "fix"}],
            "iteration_complete": False,
        })
        orchestrator._run_agent = AsyncMock(return_value="C D E F|G A B c|c B A G|F E D C|")
        orchestrator._agent_defs = {"clef-composer": {}}
        orchestrator.VOICE_MAP = {"melody": "V:1"}
        orchestrator.inter_agent_delay = 0

        # Improving: 10 -> 5 -> 1
        call_num = 0
        def improving_validation(*args, **kwargs):
            nonlocal call_num
            call_num += 1
            return [{"category": "duration", "voice": "V:1", "message": "measure too long", "severity": "FAIL"}] * max(1, 11 - call_num * 5)

        with patch("clef_server.tools.merge_abc", return_value={"ok": True}):
            with patch("clef_server.tools.abc_to_midi", return_value={"ok": True}):
                with patch("clef_server.orchestrator.response_parser.extract_abc", side_effect=lambda x: x):
                    with patch("clef_server.orchestrator.score_processor.inject_midi_programs"):
                        with patch("clef_server.orchestrator.score_processor.store_fragment"):
                            with patch("clef_server.orchestrator.validation.run_validation", side_effect=improving_validation):
                                await orchestrator._phase_iterate()

        # Should have run all 3 rounds since fail_count was improving
        assert orchestrator.session.iteration_count == 3

        shutil.rmtree(tmp_path, ignore_errors=True)
