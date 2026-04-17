"""Phase 3 TDD tests: API surface, permissions, agent metadata.

Tests MUST fail first (RED), then we implement to pass (GREEN).
"""

import json
import time
from pathlib import Path

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# 改进 3: Per-session tool permissions
# ══════════════════════════════════════════════════════════════════════════════


class TestToolPermissions:
    """Test ToolPermissions three-layer decision: deny > override > base."""

    def test_deny_blocks_even_if_in_base_map(self) -> None:
        from clef_server.sessions import ToolPermissions

        perms = ToolPermissions(denied_tools=frozenset({"write_file"}))
        base_map = {"clef-composer": ["read_file", "write_file"]}

        assert perms.is_tool_allowed("write_file", "clef-composer", base_map) is False

    def test_override_grants_beyond_base_map(self) -> None:
        """Override grants tool access even if not in base map."""
        from clef_server.sessions import ToolPermissions

        perms = ToolPermissions(allowed_overrides=frozenset({"inject_expression"}))
        base_map = {"clef-composer": ["read_file", "write_file"]}

        # inject_expression not in composer's base map, but override grants it
        assert perms.is_tool_allowed("inject_expression", "clef-composer", base_map) is True

    def test_override_in_base_allowed(self) -> None:
        """Override re-enables a tool that would otherwise be available."""
        from clef_server.sessions import ToolPermissions

        perms = ToolPermissions(allowed_overrides=frozenset({"write_file"}))
        base_map = {"clef-composer": ["read_file", "write_file"]}

        assert perms.is_tool_allowed("write_file", "clef-composer", base_map) is True

    def test_no_overrides_base_map_applies(self) -> None:
        from clef_server.sessions import ToolPermissions

        perms = ToolPermissions()
        base_map = {"clef-composer": ["read_file", "write_file"]}

        assert perms.is_tool_allowed("read_file", "clef-composer", base_map) is True
        assert perms.is_tool_allowed("validate_abc", "clef-composer", base_map) is False

    def test_deny_takes_precedence_over_override(self) -> None:
        from clef_server.sessions import ToolPermissions

        perms = ToolPermissions(
            denied_tools=frozenset({"write_file"}),
            allowed_overrides=frozenset({"write_file"}),
        )
        base_map = {"clef-composer": ["read_file", "write_file"]}

        assert perms.is_tool_allowed("write_file", "clef-composer", base_map) is False

    def test_default_permissions_allow_base(self) -> None:
        """Default ToolPermissions (empty) doesn't restrict anything."""
        from clef_server.sessions import ToolPermissions

        perms = ToolPermissions()
        base_map = {"clef-composer": ["read_file"]}

        assert perms.is_tool_allowed("read_file", "clef-composer", base_map) is True


class TestToolPermissionsOnSession:
    """Test that ComposeSession has tool_permissions field."""

    def test_session_has_tool_permissions(self, tmp_path: Path) -> None:
        from clef_server.sessions import ComposeSession, ToolPermissions

        session = ComposeSession(session_id="s1", workdir=str(tmp_path))
        assert hasattr(session, "tool_permissions")
        assert isinstance(session.tool_permissions, ToolPermissions)

    def test_session_with_custom_permissions(self, tmp_path: Path) -> None:
        from clef_server.sessions import ComposeSession, ToolPermissions

        perms = ToolPermissions(denied_tools=frozenset({"write_file"}))
        session = ComposeSession(session_id="s1", workdir=str(tmp_path), tool_permissions=perms)
        assert "write_file" in session.tool_permissions.denied_tools


# ══════════════════════════════════════════════════════════════════════════════
# 改进 4: Agent metadata (% ClefMeta comments)
# ══════════════════════════════════════════════════════════════════════════════


class TestAgentMetadata:
    """Test stamp_agent_meta produces valid ABC comment."""

    def test_stamp_produces_comment_line(self) -> None:
        from clef_server import score_processor

        result = score_processor.stamp_agent_meta("X:1\nK:C\nC |", "clef-composer", "V:1", 1)

        lines = result.split("\n")
        assert lines[0].startswith("% ClefMeta:")
        meta = json.loads(lines[0].replace("% ClefMeta: ", ""))
        assert meta["agent"] == "clef-composer"
        assert meta["voice"] == "V:1"
        assert meta["round"] == 1
        assert "timestamp" in meta

    def test_stamp_preserves_original_content(self) -> None:
        from clef_server import score_processor

        content = "X:1\nK:C\nC E G |"
        result = score_processor.stamp_agent_meta(content, "clef-composer", "V:1", 1)

        # Original content preserved after meta line
        assert "X:1" in result
        assert "K:C" in result
        assert "C E G |" in result

    def test_meta_line_is_valid_abc_comment(self) -> None:
        """% prefix is standard ABC comment syntax."""
        from clef_server import score_processor

        result = score_processor.stamp_agent_meta("X:1", "clef-harmonist", "V:2", 3)

        meta_line = result.split("\n")[0]
        assert meta_line.startswith("%")  # ABC comment

    def test_multiple_stamps_stacked(self) -> None:
        """Multiple agents can stamp the same file."""
        from clef_server import score_processor

        content = "X:1\nK:C\nV:1\nC |"
        stamped1 = score_processor.stamp_agent_meta(content, "clef-composer", "V:1", 1)
        stamped2 = score_processor.stamp_agent_meta(stamped1, "clef-harmonist", "V:2", 1)

        meta_lines = [l for l in stamped2.split("\n") if l.startswith("% ClefMeta:")]
        assert len(meta_lines) == 2


# ══════════════════════════════════════════════════════════════════════════════
# Cancel check in _advance_phase
# ══════════════════════════════════════════════════════════════════════════════


class TestAdvancePhaseCancelCheck:
    """Test _advance_phase respects cancel_requested."""

    @pytest.mark.asyncio
    async def test_advance_phase_cancels_when_requested(self, tmp_path: Path) -> None:
        """_advance_phase should cancel session if cancel_requested is True."""
        from clef_server.orchestrator import ComposeOrchestrator
        from clef_server.sessions import SessionManager, ComposeSession

        mgr = SessionManager()
        session = mgr.create("test", workdir=str(tmp_path), session_id="test-cancel-1")
        session.set_running()

        # Monkey-patch get_session_manager to return our mgr
        import clef_server.orchestrator as orch_mod
        original_mgr = orch_mod._session_manager
        orch_mod._session_manager = mgr

        try:
            orch = ComposeOrchestrator(
                session_id="test-cancel-1",
                providers={},
                workdir=str(tmp_path),
            )
            session.request_cancel()

            await orch._advance_phase("parse")

            assert session.status == "cancelled"
        finally:
            orch_mod._session_manager = original_mgr
