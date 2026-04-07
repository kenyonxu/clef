"""Tests for routes.py — FastAPI endpoint tests using httpx.AsyncClient."""

import pytest
from httpx import ASGITransport, AsyncClient

from clef_server.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestComposeEndpoint:
    async def test_create_compose_session(self, client: AsyncClient):
        resp = await client.post("/compose", json={
            "prompt": "Write a happy song",
            "plan": {"title": "Happy", "key": "C", "tempo": 120},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["status"] == "created"

    async def test_create_compose_missing_prompt(self, client: AsyncClient):
        resp = await client.post("/compose", json={})
        assert resp.status_code == 422


class TestStatusEndpoint:
    async def test_get_status(self, client: AsyncClient):
        create_resp = await client.post("/compose", json={"prompt": "test"})
        session_id = create_resp.json()["session_id"]
        resp = await client.get(f"/status/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["status"] == "created"

    async def test_get_status_nonexistent(self, client: AsyncClient):
        resp = await client.get("/status/nonexistent")
        assert resp.status_code == 404


class TestSessionsEndpoint:
    async def test_list_sessions(self, client: AsyncClient):
        await client.post("/compose", json={"prompt": "s1"})
        await client.post("/compose", json={"prompt": "s2"})
        resp = await client.get("/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) >= 2


class TestCancelEndpoint:
    async def test_cancel_session(self, client: AsyncClient):
        create_resp = await client.post("/compose", json={"prompt": "cancel me"})
        session_id = create_resp.json()["session_id"]
        resp = await client.post(f"/cancel/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"

    async def test_cancel_nonexistent(self, client: AsyncClient):
        resp = await client.post("/cancel/nonexistent")
        assert resp.status_code == 404


class TestResultEndpoint:
    async def test_result_not_done(self, client: AsyncClient):
        create_resp = await client.post("/compose", json={"prompt": "test"})
        session_id = create_resp.json()["session_id"]
        resp = await client.get(f"/result/{session_id}")
        assert resp.status_code == 400


class TestConfirmEndpoint:
    async def test_confirm_not_awaiting(self, client: AsyncClient):
        create_resp = await client.post("/compose", json={"prompt": "test"})
        session_id = create_resp.json()["session_id"]
        resp = await client.post(f"/confirm/{session_id}", json={"action": "continue"})
        assert resp.status_code == 400

    async def test_confirm_missing_body(self, client: AsyncClient):
        create_resp = await client.post("/compose", json={"prompt": "test"})
        session_id = create_resp.json()["session_id"]
        resp = await client.post(f"/confirm/{session_id}")
        assert resp.status_code == 422
