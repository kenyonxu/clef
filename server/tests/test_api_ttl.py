"""API endpoints + Session TTL TDD tests.

Covers:
- PATCH /sessions/{id}/permissions
- GET /sessions/{id}/permissions
- GET /tools
- Session TTL in SessionManager
"""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _create_app():
    """Create a FastAPI test app with routes."""
    from fastapi import FastAPI
    from clef_server.routes import create_router
    app = FastAPI()
    app.include_router(create_router(), prefix="/api")
    return app


def _get_client():
    return TestClient(_create_app())


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /sessions/{id}/permissions
# ══════════════════════════════════════════════════════════════════════════════


class TestPatchPermissions:
    """Test PATCH /sessions/{id}/permissions endpoint."""

    def test_patch_permissions_returns_200(self) -> None:
        client = _get_client()
        from clef_server.orchestrator import get_session_manager

        mgr = get_session_manager()
        session = mgr.create("test", workdir="/tmp/test")

        resp = client.patch(
            f"/api/sessions/{session.session_id}/permissions",
            json={"denied_tools": ["write_file"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "write_file" in data["denied_tools"]

    def test_patch_permissions_validates_body(self) -> None:
        """Invalid body returns 422 (Pydantic validation)."""
        client = _get_client()

        resp = client.patch("/api/sessions/nonexistent/permissions", json={})
        # Should be 422 (missing required field) or 404
        assert resp.status_code in (404, 422)

    def test_patch_nonexistent_session_returns_404(self) -> None:
        client = _get_client()

        resp = client.patch(
            "/api/sessions/nonexistent/permissions",
            json={"denied_tools": ["write_file"]},
        )
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# GET /sessions/{id}/permissions
# ══════════════════════════════════════════════════════════════════════════════


class TestGetPermissions:
    """Test GET /sessions/{id}/permissions endpoint."""

    def test_get_permissions_default(self) -> None:
        client = _get_client()
        from clef_server.orchestrator import get_session_manager

        mgr = get_session_manager()
        session = mgr.create("test", workdir="/tmp/test")

        resp = client.get(f"/api/sessions/{session.session_id}/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["denied_tools"] == []
        assert data["allowed_overrides"] == []

    def test_get_permissions_after_patch(self) -> None:
        client = _get_client()
        from clef_server.orchestrator import get_session_manager

        mgr = get_session_manager()
        session = mgr.create("test", workdir="/tmp/test")

        # Patch first
        client.patch(
            f"/api/sessions/{session.session_id}/permissions",
            json={"denied_tools": ["write_file", "merge_abc"]},
        )

        # Then GET
        resp = client.get(f"/api/sessions/{session.session_id}/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["denied_tools"]) == {"write_file", "merge_abc"}

    def test_get_nonexistent_session_returns_404(self) -> None:
        client = _get_client()
        resp = client.get("/api/sessions/nonexistent/permissions")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# GET /tools
# ══════════════════════════════════════════════════════════════════════════════


class TestGetTools:
    """Test GET /tools endpoint."""

    def test_get_tools_returns_all(self) -> None:
        client = _get_client()

        resp = client.get("/api/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 8
        names = {t["name"] for t in data}
        assert "read_file" in names
        assert "write_file" in names
        assert "validate_abc" in names

    def test_get_tools_includes_safety(self) -> None:
        client = _get_client()

        resp = client.get("/api/tools")
        data = resp.json()
        for tool in data:
            assert "name" in tool
            assert "safety" in tool


# ══════════════════════════════════════════════════════════════════════════════
# Session TTL
# ══════════════════════════════════════════════════════════════════════════════


class TestSessionTTL:
    """Test SessionManager TTL enforcement."""

    def test_expired_session_returns_none(self) -> None:
        from clef_server.sessions import SessionManager

        mgr = SessionManager(ttl_seconds=1)
        session = mgr.create("test", workdir="/tmp/test")
        session.created_at = time.time() - 2  # expired

        assert mgr.get(session.session_id) is None

    def test_fresh_session_available(self) -> None:
        from clef_server.sessions import SessionManager

        mgr = SessionManager(ttl_seconds=3600)
        session = mgr.create("test", workdir="/tmp/test")
        assert mgr.get(session.session_id) is not None

    def test_default_ttl_is_infinite(self) -> None:
        """Without ttl_seconds, sessions never expire."""
        from clef_server.sessions import SessionManager

        mgr = SessionManager()
        session = mgr.create("test", workdir="/tmp/test")
        session.created_at = time.time() - 86400  # 1 day ago
        assert mgr.get(session.session_id) is not None
