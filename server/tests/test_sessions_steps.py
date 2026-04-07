"""Tests for ComposeSession workflow step tracking."""

from clef_server.sessions import ComposeSession, PHASES, PHASE_ORDER


class TestWorkflowSteps:
    def test_default_steps_are_all_pending(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
            user_prompt="test prompt",
        )
        steps = session.get_workflow_steps()
        assert len(steps) == 6
        assert all(s["status"] == "pending" for s in steps)

    def test_record_phase_updates_status(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
        )
        session.set_running()
        session.record_phase("parse", "running")

        steps = session.get_workflow_steps()
        assert steps[0]["status"] == "running"
        assert steps[0]["id"] == "parse"
        assert steps[1]["status"] == "pending"

    def test_record_phase_done_marks_completed(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
        )
        session.set_running()
        session.record_phase("parse", "running")
        session.record_phase("parse", "done")

        steps = session.get_workflow_steps()
        assert steps[0]["status"] == "done"

    def test_failed_phase_sets_error(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
        )
        session.set_running()
        session.record_phase("sample", "failed", error="Plan generation failed")

        steps = session.get_workflow_steps()
        assert steps[1]["status"] == "failed"
        assert steps[1]["error"] == "Plan generation failed"

    def test_to_dict_includes_workflow_steps(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
            user_prompt="test",
        )
        session.set_running()
        session.record_phase("parse", "done")
        session.record_phase("sample", "running")

        data = session.to_dict()
        assert "workflow_steps" in data
        assert data["workflow_steps"][0]["status"] == "done"
        assert data["workflow_steps"][1]["status"] == "running"

    def test_phases_constant(self):
        assert len(PHASES) == 6
        assert PHASES[0]["id"] == "parse"
        assert PHASES[5]["id"] == "express"

    def test_phase_order_constant(self):
        assert len(PHASE_ORDER) == 6
        assert PHASE_ORDER == ["parse", "sample", "create", "iterate", "review", "express"]

    def test_confirm_phases(self):
        confirm_ids = {p["id"] for p in PHASES if p.get("confirm")}
        assert confirm_ids == {"parse", "sample", "review"}
