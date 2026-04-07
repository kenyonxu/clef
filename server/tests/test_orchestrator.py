"""Tests for ComposeOrchestrator -- Phase 0 (parse + plan) and navigation."""

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
    "sections": [],
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
        # Simulate: parse completed, awaiting confirm
        session.set_running()
        session.record_phase("parse", "done")
        session.set_awaiting_confirm({
            "phase": "parse",
            "title": "确认音乐规划",
            "plan": {},
        })

        with patch.object(orch, "_phase_sample", new_callable=AsyncMock) as mock_sample:
            await orch.resume()
            mock_sample.assert_called_once_with(feedback=None)

    @pytest.mark.asyncio
    async def test_resume_from_parse_ignores_user_feedback(self, orch, session, tmp_path):
        """H1: feedback param is ignored when resuming from parse."""
        session.set_running()
        session.record_phase("parse", "done")
        session.set_awaiting_confirm({"phase": "parse", "plan": {}})

        with patch.object(orch, "_phase_sample", new_callable=AsyncMock) as mock_sample:
            await orch.resume(user_feedback="change the key to Dm")
            # feedback=None is passed, NOT the user's feedback
            mock_sample.assert_called_once_with(feedback=None)

    @pytest.mark.asyncio
    async def test_resume_not_awaiting_raises(self, orch, session):
        """resume() should raise if session is not awaiting_confirm."""
        session.set_running()
        with pytest.raises(RuntimeError, match="not awaiting"):
            await orch.resume()


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
        (output_dir / "final.mid").write_text("fake")

        await orch._advance_phase("express")
        assert session.status == "done"
        assert "output/final.mid" in session.output_files


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
        (output / "final.mid").write_text("data")
        (output / "score.abc").write_text("notes")

        result = orch._collect_outputs()
        assert len(result) == 2
        assert "output/final.mid" in result
        assert "output/score.abc" in result
