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

    def test_phases_constant(self):
        from clef_server.sessions import PHASES, PHASE_ORDER
        assert len(PHASES) == 6
        assert PHASES[0]["id"] == "parse"
        assert PHASE_ORDER[0] == "parse"
        assert sum(1 for p in PHASES if p["confirm"]) == 3

    def test_set_awaiting_confirm_with_data(self, tmp_path: Path):
        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_awaiting_confirm({"phase": "parse", "plan": {"key": "C"}})
        assert session.status == "awaiting_confirm"
        assert session.confirmation_data["plan"]["key"] == "C"

    def test_record_phase(self, tmp_path: Path):
        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.record_phase("parse", "done")
        session.record_phase("sample", "done")
        assert len(session.phase_history) == 2
        assert session.phase_history[0]["phase"] == "parse"

    def test_get_workflow_steps_from_phases(self, tmp_path: Path):
        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.record_phase("parse", "done")
        steps = session.get_workflow_steps()
        assert steps[0]["status"] == "done"
        assert steps[1]["status"] == "pending"

    def test_to_dict_includes_new_fields(self, tmp_path: Path):
        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.record_phase("parse", "running")
        d = session.to_dict()
        assert "current_phase" in d
        assert "confirmation_data" in d
        assert "phase_history" in d
        assert "sample_round" in d
        assert "iteration_count" in d
        assert d["current_phase"] == "parse"


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


class TestSessionSerialization:
    def test_roundtrip_basic(self, tmp_path):
        mgr = SessionManager()
        s = mgr.create("test prompt", str(tmp_path))
        s.set_running()
        s.record_phase("parse", "done")
        s.set_awaiting_confirm({"phase": "parse", "plan": {"title": "test"}})

        data = s.to_persist_dict()
        restored = ComposeSession.from_dict(data)

        assert restored.session_id == s.session_id
        assert restored.status == s.status
        assert restored.current_phase == s.current_phase
        assert restored.confirmation_data == s.confirmation_data
        assert len(restored.phase_history) == len(s.phase_history)

    def test_roundtrip_preserves_iteration_count(self, tmp_path):
        mgr = SessionManager()
        s = mgr.create("test", str(tmp_path))
        s.iteration_count = 2
        data = s.to_persist_dict()
        restored = ComposeSession.from_dict(data)
        assert restored.iteration_count == 2

    def test_from_dict_omits_event_queues(self, tmp_path):
        """Event queues are runtime-only, not serialized."""
        mgr = SessionManager()
        s = mgr.create("test", str(tmp_path))
        data = s.to_persist_dict()
        restored = ComposeSession.from_dict(data)
        assert len(restored._event_queues) == 0


class TestSessionPersistence:
    def test_save_and_restore(self, tmp_path):
        persist_dir = tmp_path / "persist"
        mgr = SessionManager(persist_dir=str(persist_dir))
        s = mgr.create("test prompt", str(tmp_path / "work"))
        s.set_running()
        s.record_phase("parse", "done")

        mgr.persist(s)

        mgr2 = SessionManager(persist_dir=str(persist_dir))
        restored = mgr2.restore(s.session_id)
        assert restored is not None
        assert restored.session_id == s.session_id
        assert restored.status == "running"

    def test_restore_nonexistent_returns_none(self, tmp_path):
        persist_dir = tmp_path / "persist"
        mgr = SessionManager(persist_dir=str(persist_dir))
        assert mgr.restore("no-such-id") is None

    def test_remove_deletes_file(self, tmp_path):
        persist_dir = tmp_path / "persist"
        mgr = SessionManager(persist_dir=str(persist_dir))
        s = mgr.create("test", str(tmp_path))
        mgr.persist(s)
        mgr.remove(s.session_id)
        assert mgr.restore(s.session_id) is None

    def test_restore_all_incomplete_skips_terminal(self, tmp_path):
        persist_dir = tmp_path / "persist"
        mgr = SessionManager(persist_dir=str(persist_dir))
        s1 = mgr.create("running session", str(tmp_path))
        s1.set_running()
        s2 = mgr.create("done session", str(tmp_path))
        s2.set_running()
        s2.set_done()
        mgr.persist(s1)
        mgr.persist(s2)

        mgr2 = SessionManager(persist_dir=str(persist_dir))
        restored = mgr2.restore_all_incomplete()
        assert len(restored) == 1
        assert restored[0].session_id == s1.session_id

    def test_corrupted_json_returns_none(self, tmp_path):
        persist_dir = tmp_path / "persist"
        persist_dir.mkdir()
        mgr = SessionManager(persist_dir=str(persist_dir))
        (persist_dir / "clef-bad123.json").write_text("{invalid json", encoding="utf-8")
        assert mgr.restore("clef-bad123") is None

    def test_no_persist_dir_is_noop(self, tmp_path):
        mgr = SessionManager()
        s = mgr.create("test", str(tmp_path))
        mgr.persist(s)  # Should not raise
        assert mgr.restore(s.session_id) is None
        assert mgr.restore_all_incomplete() == []
