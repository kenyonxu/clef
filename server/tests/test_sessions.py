"""Tests for sessions.py — session lifecycle management."""

from pathlib import Path

import pytest

from clef_server.sessions import SessionManager, ComposeSession


class TestComposeSession:
    def test_create_session(self, tmp_path: Path):
        session = ComposeSession(session_id="test-123", workdir=str(tmp_path), user_prompt="Write a happy song")
        assert session.session_id == "test-123"
        assert session.status == "created"
        assert session.user_prompt == "Write a happy song"

    def test_transition_to_running(self, tmp_path: Path):
        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        assert session.status == "running"

    def test_transition_to_done(self, tmp_path: Path):
        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_done(output_files=["final.mid"])
        assert session.status == "done"
        assert session.output_files == ["final.mid"]

    def test_transition_to_failed(self, tmp_path: Path):
        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_failed(error="LLM timeout")
        assert session.status == "failed"
        assert session.error == "LLM timeout"

    def test_invalid_transition_raises(self, tmp_path: Path):
        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        with pytest.raises(ValueError, match="Cannot transition"):
            session.set_done()

    def test_set_awaiting_confirm(self, tmp_path: Path):
        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_awaiting_confirm()
        assert session.status == "awaiting_confirm"

    def test_to_dict(self, tmp_path: Path):
        session = ComposeSession(session_id="s1", workdir=str(tmp_path), user_prompt="test")
        d = session.to_dict()
        assert d["session_id"] == "s1"
        assert d["status"] == "created"
        assert "created_at" in d


class TestSessionManager:
    def test_create_session(self):
        mgr = SessionManager()
        session = mgr.create("Write a jazz piece", workdir="/tmp/test")
        assert session.session_id.startswith("clef-")
        assert session.status == "created"
        assert mgr.get(session.session_id) is not None

    def test_get_nonexistent_returns_none(self):
        mgr = SessionManager()
        assert mgr.get("nonexistent") is None

    def test_list_sessions(self):
        mgr = SessionManager()
        mgr.create("Song 1", workdir="/tmp/a")
        mgr.create("Song 2", workdir="/tmp/b")
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_remove_session(self):
        mgr = SessionManager()
        s = mgr.create("temp", workdir="/tmp")
        assert mgr.remove(s.session_id) is True
        assert mgr.get(s.session_id) is None

    def test_remove_nonexistent(self):
        mgr = SessionManager()
        assert mgr.remove("nope") is False
