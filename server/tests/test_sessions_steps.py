"""Tests for ComposeSession workflow step tracking."""

from clef_server.sessions import ComposeSession, WORKFLOW_STEPS


class TestWorkflowSteps:
    def test_default_steps_are_all_pending(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
            user_prompt="test prompt",
        )
        steps = session.get_workflow_steps()
        assert len(steps) == 4
        assert all(s["status"] == "pending" for s in steps)

    def test_advance_step_marks_done_and_next_running(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
        )
        session.set_running()
        session.update_step(0, "running")

        steps = session.get_workflow_steps()
        assert steps[0]["status"] == "running"
        assert steps[1]["status"] == "pending"

        session.advance_step(0)
        steps = session.get_workflow_steps()
        assert steps[0]["status"] == "done"
        assert steps[1]["status"] == "running"

    def test_failed_step_sets_error(self):
        session = ComposeSession(
            session_id="clef-test",
            workdir="/tmp/test",
        )
        session.set_running()
        session.update_step(1, "failed", error="Plan generation failed")

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
        session.update_step(0, "done")
        session.update_step(1, "running")

        data = session.to_dict()
        assert "workflow_steps" in data
        assert data["workflow_steps"][0]["status"] == "done"
        assert data["workflow_steps"][1]["status"] == "running"

    def test_workflow_steps_constant(self):
        assert len(WORKFLOW_STEPS) == 4
        assert WORKFLOW_STEPS[0]["name"] == "parse"
        assert WORKFLOW_STEPS[3]["name"] == "inject"
