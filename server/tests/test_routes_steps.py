"""Tests for StatusResponse with workflow_steps."""

import pytest
from fastapi.testclient import TestClient
from clef_server.app import create_app
from clef_server.sessions import SessionManager


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def session_mgr():
    return SessionManager()


class TestStatusResponseWithSteps:
    def test_status_includes_workflow_steps(self, client, session_mgr, monkeypatch):
        monkeypatch.setattr("clef_server.routes._session_manager", session_mgr)
        session = session_mgr.create("test prompt", "/tmp/test")
        session.set_running()
        session.update_step(0, "done")
        session.update_step(1, "running")

        response = client.get(f"/status/{session.session_id}")
        assert response.status_code == 200
        data = response.json()
        assert "workflow_steps" in data
        assert data["workflow_steps"][0]["status"] == "done"
        assert data["workflow_steps"][1]["status"] == "running"
        assert len(data["workflow_steps"]) == 4
