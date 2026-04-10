"""Phase 1 TDD tests: Critical security + graceful shutdown.

Tests MUST fail first (RED), then we implement to pass (GREEN).

Covers:
- CRITICAL: Path traversal guard in tools.py
- CRITICAL: Graceful shutdown + terminal guard in sessions.py
- Tool safety metadata registry (_TOOL_META)
"""

import json
from pathlib import Path

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# CRITICAL FIX: Path traversal guard (tools.py)
# ══════════════════════════════════════════════════════════════════════════════


class TestPathTraversalGuard:
    """Test that read_file and write_file reject paths outside workdir."""

    def test_write_file_rejects_path_traversal(self, tmp_path: Path) -> None:
        """write_file with ../../etc/passwd must be rejected."""
        from clef_server.tools import write_file

        workdir = tmp_path / "workdir"
        workdir.mkdir()
        traversal_path = str(workdir / ".." / ".." / "etc" / "passwd")

        with pytest.raises(ValueError, match="path traversal|outside.*workdir"):
            write_file(traversal_path, "malicious content", workdir=str(workdir))

    def test_write_file_rejects_absolute_path_outside(self, tmp_path: Path) -> None:
        """write_file with absolute path outside workdir must be rejected."""
        from clef_server.tools import write_file

        workdir = tmp_path / "workdir"
        workdir.mkdir()

        with pytest.raises(ValueError, match="outside.*workdir"):
            write_file("/etc/passwd", "malicious", workdir=str(workdir))

    def test_write_file_allows_path_inside_workdir(self, tmp_path: Path) -> None:
        """write_file with normal relative path inside workdir works."""
        from clef_server.tools import write_file

        workdir = tmp_path / "workdir"
        workdir.mkdir()
        target = workdir / "subdir" / "score.abc"

        result = write_file(str(target), "X:1\nK:C\nC |", workdir=str(workdir))
        assert result["path"] == str(target)
        assert target.read_text(encoding="utf-8") == "X:1\nK:C\nC |"

    def test_write_file_requires_workdir(self, tmp_path: Path) -> None:
        """write_file without workdir raises TypeError (security: always validate)."""
        from clef_server.tools import write_file

        target = tmp_path / "score.abc"
        with pytest.raises(TypeError):
            write_file(str(target), "X:1\nK:C\nC |")

    def test_read_file_rejects_path_traversal(self, tmp_path: Path) -> None:
        """read_file with ../../etc/passwd must be rejected."""
        from clef_server.tools import read_file

        workdir = tmp_path / "workdir"
        workdir.mkdir()
        traversal_path = str(workdir / ".." / ".." / "etc" / "passwd")

        with pytest.raises(ValueError, match="path traversal|outside.*workdir"):
            read_file(traversal_path, workdir=str(workdir))

    def test_read_file_rejects_absolute_path_outside(self, tmp_path: Path) -> None:
        """read_file with /etc/passwd must be rejected when workdir set."""
        from clef_server.tools import read_file

        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "safe.txt").write_text("safe", encoding="utf-8")

        with pytest.raises(ValueError, match="outside.*workdir"):
            read_file("/etc/passwd", workdir=str(workdir))

    def test_read_file_allows_path_inside_workdir(self, tmp_path: Path) -> None:
        """read_file with normal path inside workdir works."""
        from clef_server.tools import read_file

        workdir = tmp_path / "workdir"
        workdir.mkdir()
        target = workdir / "score.abc"
        target.write_text("X:1\nK:C\nC |", encoding="utf-8")

        result = read_file(str(target), workdir=str(workdir))
        assert "X:1" in result


# ══════════════════════════════════════════════════════════════════════════════
# CRITICAL FIX + 改进 5: Graceful shutdown + terminal guard (sessions.py)
# ══════════════════════════════════════════════════════════════════════════════


class TestTerminalGuard:
    """Test is_terminal guard and terminal state enforcement."""

    def test_is_terminal_returns_true_for_done(self, tmp_path: Path) -> None:
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_done()
        assert session.is_terminal is True

    def test_is_terminal_returns_true_for_failed(self, tmp_path: Path) -> None:
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_failed(error="boom")
        assert session.is_terminal is True

    def test_is_terminal_returns_true_for_cancelled(self, tmp_path: Path) -> None:
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_cancelled()
        assert session.is_terminal is True

    def test_is_terminal_returns_false_for_created(self, tmp_path: Path) -> None:
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        assert session.is_terminal is False

    def test_is_terminal_returns_false_for_running(self, tmp_path: Path) -> None:
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        assert session.is_terminal is False

    def test_is_terminal_returns_false_for_awaiting_confirm(self, tmp_path: Path) -> None:
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_awaiting_confirm()
        assert session.is_terminal is False

    def test_transition_on_terminal_raises(self, tmp_path: Path) -> None:
        """Cannot transition away from a terminal state."""
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_done()

        with pytest.raises(ValueError, match="terminal"):
            session.set_running()

    def test_terminal_states_constant(self) -> None:
        """TERMINAL_STATES contains done, failed, cancelled."""
        from clef_server.sessions import TERMINAL_STATES

        assert TERMINAL_STATES == frozenset({"done", "failed", "cancelled"})


class TestGracefulCancel:
    """Test request_cancel + cancel_requested for graceful shutdown."""

    def test_request_cancel_on_running_session(self, tmp_path: Path) -> None:
        """request_cancel sets flag but doesn't change status."""
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()

        session.request_cancel()
        assert session.cancel_requested is True
        assert session.status == "running"  # status unchanged

    def test_request_cancel_on_awaiting_confirm(self, tmp_path: Path) -> None:
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_awaiting_confirm()

        session.request_cancel()
        assert session.cancel_requested is True
        assert session.status == "awaiting_confirm"

    def test_request_cancel_on_terminal_is_noop(self, tmp_path: Path) -> None:
        """request_cancel on a done session does nothing."""
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        session.set_running()
        session.set_done()

        session.request_cancel()  # should not raise
        assert session.cancel_requested is False  # flag not set

    def test_cancel_requested_defaults_false(self, tmp_path: Path) -> None:
        from clef_server.sessions import ComposeSession

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        assert session.cancel_requested is False


# ══════════════════════════════════════════════════════════════════════════════
# Tool safety metadata (prerequisite for Phase 2 concurrency)
# ══════════════════════════════════════════════════════════════════════════════


class TestToolMeta:
    """Test _TOOL_META registry covers all 8 tools."""

    def test_tool_meta_covers_all_tools(self) -> None:
        """Every tool in TOOLS_REGISTRY must have a _TOOL_META entry."""
        from clef_server.tools import TOOLS_REGISTRY, _TOOL_META

        for tool_name in TOOLS_REGISTRY:
            assert tool_name in _TOOL_META, f"{tool_name} missing from _TOOL_META"

    def test_tool_safety_enum_values(self) -> None:
        from clef_server.tools import ToolSafety

        assert ToolSafety.READ_ONLY.value == "read_only"
        assert ToolSafety.IDEMPOTENT_WRITE.value == "idempotent"
        assert ToolSafety.EXCLUSIVE_WRITE.value == "exclusive"

    def test_read_only_tools_are_labeled(self) -> None:
        """validate_abc, abc_lint, abc_to_midi, read_file should be READ_ONLY."""
        from clef_server.tools import _TOOL_META, ToolSafety

        read_only_tools = {"read_file", "validate_abc", "abc_lint", "abc_to_midi"}
        for name in read_only_tools:
            assert _TOOL_META[name].safety == ToolSafety.READ_ONLY, (
                f"{name} should be READ_ONLY"
            )

    def test_exclusive_write_tools_are_labeled(self) -> None:
        """write_file, merge_abc, inject_expression should be EXCLUSIVE_WRITE."""
        from clef_server.tools import _TOOL_META, ToolSafety

        exclusive_tools = {"write_file", "merge_abc", "inject_expression"}
        for name in exclusive_tools:
            assert _TOOL_META[name].safety == ToolSafety.EXCLUSIVE_WRITE, (
                f"{name} should be EXCLUSIVE_WRITE"
            )

    def test_snapshot_is_idempotent(self) -> None:
        from clef_server.tools import _TOOL_META, ToolSafety

        assert _TOOL_META["snapshot"].safety == ToolSafety.IDEMPOTENT_WRITE

    def test_tool_meta_has_estimated_tokens(self) -> None:
        """Each ToolMeta entry should have a reasonable estimated_tokens."""
        from clef_server.tools import _TOOL_META

        for name, meta in _TOOL_META.items():
            assert isinstance(meta.estimated_tokens, int)
            assert meta.estimated_tokens > 0, f"{name} has invalid estimated_tokens"
