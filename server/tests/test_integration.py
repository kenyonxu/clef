"""Integration tests — full compose pipeline with mocked LLM."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

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


class TestComposeIntegration:
    async def test_compose_with_plan(self, client: AsyncClient):
        resp = await client.post("/compose", json={
            "prompt": "A cheerful melody in C major",
            "plan": SAMPLE_PLAN,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data

    async def test_compose_without_plan(self, client: AsyncClient):
        resp = await client.post("/compose", json={"prompt": "A sad waltz"})
        assert resp.status_code == 200

    async def test_full_lifecycle(self, client: AsyncClient):
        create = await client.post("/compose", json={"prompt": "lifecycle test"})
        sid = create.json()["session_id"]

        status = await client.get(f"/status/{sid}")
        assert status.json()["status"] == "created"

        cancel = await client.post(f"/cancel/{sid}")
        assert cancel.json()["status"] == "cancelled"

        status2 = await client.get(f"/status/{sid}")
        assert status2.json()["status"] == "cancelled"

    async def test_double_cancel_idempotent(self, client: AsyncClient):
        create = await client.post("/compose", json={"prompt": "double cancel"})
        sid = create.json()["session_id"]
        await client.post(f"/cancel/{sid}")
        resp = await client.post(f"/cancel/{sid}")
        assert resp.status_code == 400  # already cancelled
