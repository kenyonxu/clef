"""Integration tests — full compose pipeline with mocked LLM."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from clef_server.app import create_app
from clef_server.orchestrator import get_session_manager


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear the shared session manager before and after each test."""
    mgr = get_session_manager()
    mgr._sessions.clear()
    yield
    mgr._sessions.clear()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


SAMPLE_PLAN = {
    "title": "Cheerful",
    "key": "C",
    "time_signature": "4/4",
    "tempo": 120,
    "total_bars": 8,
    "structure": {"sections": [{"name": "A", "bars": 8}]},
    "voices": {
        "1": {"role": "melody", "instrument": "Piano", "range": {"min": 60, "max": 84}, "register": {"min": 60, "max": 79}},
        "2": {"role": "harmony", "instrument": "Piano", "range": {"min": 48, "max": 72}, "register": {"min": 55, "max": 72}},
        "3": {"role": "bass", "instrument": "Bass", "range": {"min": 28, "max": 55}, "register": {"min": 36, "max": 48}},
        "4": {"role": "drums", "instrument": "Kit", "range": {"min": 35, "max": 81}, "register": {"min": 35, "max": 81}},
    },
    "generation_order": ["harmony", "melody", "rhythm"],
}


class TestComposeWorkflow:
    """Tests for the phase-based compose workflow via routes."""

    async def test_compose_creates_session(self, client: AsyncClient):
        """POST /compose creates a session and returns session_id."""
        resp = await client.post("/compose", json={"prompt": "Write a happy song"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"].startswith("clef-")
        assert data["status"] == "created"

    async def test_status_returns_phase_fields(self, client: AsyncClient):
        """GET /status returns new phase-related fields."""
        resp = await client.post("/compose", json={"prompt": "test"})
        session_id = resp.json()["session_id"]

        status_resp = await client.get(f"/status/{session_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert "current_phase" in data
        assert "confirmation_data" in data
        assert "sample_round" in data
        assert "iteration_count" in data
        assert data["current_phase"] == "parse"

    async def test_full_lifecycle(self, client: AsyncClient):
        """Create -> status -> cancel -> verify status chain."""
        create = await client.post("/compose", json={"prompt": "lifecycle test"})
        sid = create.json()["session_id"]

        status = await client.get(f"/status/{sid}")
        assert status.json()["status"] == "created"

        cancel = await client.post(f"/cancel/{sid}")
        assert cancel.json()["status"] == "cancelled"

        status2 = await client.get(f"/status/{sid}")
        assert status2.json()["status"] == "cancelled"

    async def test_double_cancel_idempotent(self, client: AsyncClient):
        """Second cancel returns 400 (already cancelled)."""
        create = await client.post("/compose", json={"prompt": "double cancel"})
        sid = create.json()["session_id"]
        await client.post(f"/cancel/{sid}")
        resp = await client.post(f"/cancel/{sid}")
        assert resp.status_code == 400

    async def test_compose_with_plan(self, client: AsyncClient):
        """POST /compose with an optional plan field."""
        resp = await client.post("/compose", json={
            "prompt": "A cheerful melody in C major",
            "plan": SAMPLE_PLAN,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data

    async def test_compose_without_plan(self, client: AsyncClient):
        """POST /compose without plan still succeeds."""
        resp = await client.post("/compose", json={"prompt": "A sad waltz"})
        assert resp.status_code == 200

    async def test_cancel_session(self, client: AsyncClient):
        """POST /cancel transitions session to cancelled."""
        resp = await client.post("/compose", json={"prompt": "cancel me"})
        session_id = resp.json()["session_id"]

        cancel_resp = await client.post(f"/cancel/{session_id}")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

    async def test_status_404_for_nonexistent(self, client: AsyncClient):
        """GET /status with unknown ID returns 404."""
        resp = await client.get("/status/nonexistent")
        assert resp.status_code == 404

    async def test_confirm_not_awaiting(self, client: AsyncClient):
        """POST /confirm on a non-awaiting session returns 400."""
        resp = await client.post("/compose", json={"prompt": "test"})
        session_id = resp.json()["session_id"]
        resp = await client.post(
            f"/confirm/{session_id}",
            json={"action": "continue"},
        )
        assert resp.status_code == 400

    async def test_confirm_missing_body(self, client: AsyncClient):
        """POST /confirm without body returns 422 validation error."""
        resp = await client.post("/compose", json={"prompt": "test"})
        session_id = resp.json()["session_id"]
        resp = await client.post(f"/confirm/{session_id}")
        assert resp.status_code == 422
