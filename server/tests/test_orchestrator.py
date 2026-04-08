"""Tests for ComposeOrchestrator -- all phases and navigation."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clef_server.orchestrator import (
    PHASE_ORDER,
    ComposeOrchestrator,
    get_session_manager,
)
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
        await orch._phase_parse("Write a boss battle music")

        plan_file = tmp_path / "plan.json"
        assert plan_file.exists()
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        assert plan["key"] == "C"
        assert plan["bpm"] == 120
        assert plan["scale"] == "major"
        assert plan["demo_length_bars"] == 8

    @pytest.mark.asyncio
    async def test_phase_parse_sets_awaiting_confirm(self, orch, session, tmp_path):
        session.set_running()
        await orch._phase_parse("Write a boss battle music")

        assert session.status == "awaiting_confirm"
        assert session.confirmation_data is not None
        assert session.confirmation_data["phase"] == "parse"
        assert session.confirmation_data["title"] == "确认音乐规划"
        assert "plan" in session.confirmation_data

    @pytest.mark.asyncio
    async def test_phase_parse_records_history(self, orch, session, tmp_path):
        session.set_running()
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
        # Create output files so _collect_outputs returns something
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "final_r1.mid").write_text("fake")

        await orch._advance_phase("express")
        assert session.status == "done"
        assert "output/final_r1.mid" in session.output_files


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
        output = tmp_path / "output"
        output.mkdir()
        (output / "final_r1.mid").write_text("data")
        (output / "score.abc").write_text("notes")

        result = orch._collect_outputs()
        assert len(result) == 2
        assert "output/final_r1.mid" in result
        assert "output/score.abc" in result


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
        result = orch._extract_abc(text)
        assert result.startswith("X:1")
        assert "C D E F" in result

    def test_extract_abc_raw(self, orch):
        text = "X:1\nT:Test\nC D E F|"
        result = orch._extract_abc(text)
        assert result == text

    def test_extract_abc_fallback(self, orch):
        text = "some raw text without abc header"
        result = orch._extract_abc(text)
        assert result == text.strip()

    def test_extract_json_from_fenced(self, orch):
        text = '```json\n{"verdict": "pass", "score": 8}\n```'
        result = orch._extract_json(text)
        assert result["verdict"] == "pass"
        assert result["score"] == 8

    def test_extract_json_plain(self, orch):
        text = '{"verdict": "revise", "issues": ["bad note"]}'
        result = orch._extract_json(text)
        assert result["verdict"] == "revise"

    def test_extract_json_fallback_on_bad_json(self, orch):
        text = "not valid json at all"
        result = orch._extract_json(text)
        assert "raw" in result
        assert result["verdict"] == "pass"


# ---------------------------------------------------------------------------
# TestPhaseSample
# ---------------------------------------------------------------------------

class TestPhaseSample:

    @pytest.mark.asyncio
    async def test_phase_sample_sets_confirm(self, session, providers, tmp_path):
        """Phase sample should end with awaiting_confirm status."""
        _setup_orchestrator(
            ComposeOrchestrator(session.session_id, providers, str(tmp_path)),
            session, tmp_path,
        )
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))

        # Patch _run_agent to return placeholder ABC (AF not available in tests)
        async def mock_run(agent_name, message, **kw):
            voice = "melody" if "composer" in agent_name else "harmony"
            return f'X:1\nT:Sample\nM:4/4\nK:C\nV:1\nC D E F|'

        orch._run_agent = mock_run

        # Patch tool functions that would fail without real scripts
        with patch("clef_server.tools.merge_abc", return_value={"output": "score.abc"}), \
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

        with patch("clef_server.tools.merge_abc", return_value={"output": "score.abc"}), \
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

        with patch("clef_server.tools.merge_abc", return_value={"output": "score.abc"}), \
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

        with patch("clef_server.tools.merge_abc", return_value={"output": "score.abc"}), \
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
        """Phase express should create output directory."""
        orch = ComposeOrchestrator(session.session_id, providers, str(tmp_path))
        _setup_orchestrator(orch, session, tmp_path)
        (tmp_path / "base_r1.mid").write_bytes(b"MThd\x00\x00\x00\x06")
        session.current_phase = "express"

        async def mock_run(agent_name, message, **kw):
            return "{}"

        orch._run_agent = mock_run

        with patch("clef_server.tools.inject_expression", return_value={"output": "output/final_r1.mid"}):
            await orch._phase_express()

        assert (tmp_path / "output").exists()

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
