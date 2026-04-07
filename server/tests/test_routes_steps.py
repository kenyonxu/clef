"""Tests for StatusResponse with workflow_steps."""

import pytest
from fastapi.testclient import TestClient

from clef_server.app import create_app
from clef_server.orchestrator import get_session_manager


@pytest.fixture(autouse=True)
def clear_sessions():
    mgr = get_session_manager()
    mgr._sessions.clear()
    yield
    mgr._sessions.clear()


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestStatusResponseWithSteps:
    def test_status_includes_workflow_steps(self, client):
        mgr = get_session_manager()
        session = mgr.create("test prompt", "/tmp/test")
        session.set_running()
        session.record_phase("parse", "done")
        session.record_phase("sample", "running")

        response = client.get(f"/status/{session.session_id}")
        assert response.status_code == 200
        data = response.json()
        assert "workflow_steps" in data
        assert data["workflow_steps"][0]["status"] == "done"
        assert data["workflow_steps"][1]["status"] == "running"
        assert len(data["workflow_steps"]) == 6
