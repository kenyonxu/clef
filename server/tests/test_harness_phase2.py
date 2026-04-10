"""Phase 2 TDD tests: Core optimizations — concurrency, microcompact, file cache.

Tests MUST fail first (RED), then we implement to pass (GREEN).
"""

import asyncio
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# 改进 1: Tool concurrency — partition_agent_calls + gather error isolation
# ══════════════════════════════════════════════════════════════════════════════


class TestPartitionAgentCalls:
    """Test _partition_agent_calls batches tools by safety."""

    def _make_call(self, tools: list[str]) -> dict:
        return {"agent": "test", "tools": tools}

    def test_all_read_only_single_batch(self) -> None:
        """All READ_ONLY tools should be in a single safe batch."""
        from clef_server.orchestrator import ComposeOrchestrator
        from clef_server.tools import ToolSafety, _TOOL_META

        # Patch _TOOL_META temporarily for controlled test
        calls = [
            self._make_call(["read_file"]),
            self._make_call(["abc_lint"]),
            self._make_call(["validate_abc"]),
        ]
        orch = object.__new__(ComposeOrchestrator)
        batches = orch._partition_agent_calls(calls)

        assert len(batches) == 1
        assert batches[0].safe is True
        assert len(batches[0].calls) == 3

    def test_all_exclusive_separate_batches(self) -> None:
        """All EXCLUSIVE_WRITE tools each get their own batch."""
        from clef_server.orchestrator import ComposeOrchestrator

        calls = [
            self._make_call(["write_file"]),
            self._make_call(["merge_abc"]),
        ]
        orch = object.__new__(ComposeOrchestrator)
        batches = orch._partition_agent_calls(calls)

        assert len(batches) == 2
        assert all(not b.safe for b in batches)

    def test_mixed_tools_correct_boundaries(self) -> None:
        """Mixed tools create correct batch boundaries."""
        from clef_server.orchestrator import ComposeOrchestrator

        calls = [
            self._make_call(["read_file"]),        # safe
            self._make_call(["abc_lint"]),         # safe (merged into batch 0)
            self._make_call(["write_file"]),       # exclusive (batch 1)
            self._make_call(["read_file"]),        # safe (batch 2)
        ]
        orch = object.__new__(ComposeOrchestrator)
        batches = orch._partition_agent_calls(calls)

        assert len(batches) == 3
        assert batches[0].safe is True
        assert batches[1].safe is False
        assert batches[2].safe is True
        assert len(batches[0].calls) == 2
        assert len(batches[1].calls) == 1
        assert len(batches[2].calls) == 1

    def test_empty_calls_returns_empty(self) -> None:
        from clef_server.orchestrator import ComposeOrchestrator

        orch = object.__new__(ComposeOrchestrator)
        batches = orch._partition_agent_calls([])
        assert batches == []

    def test_unknown_tool_treated_as_exclusive(self) -> None:
        """Unknown tool names default to EXCLUSIVE_WRITE."""
        from clef_server.orchestrator import ComposeOrchestrator

        calls = [self._make_call(["unknown_tool"])]
        orch = object.__new__(ComposeOrchestrator)
        batches = orch._partition_agent_calls(calls)

        assert len(batches) == 1
        assert batches[0].safe is False


class TestGatherErrorIsolation:
    """Test asyncio.gather with return_exceptions=True for error isolation."""

    @pytest.mark.asyncio
    async def test_one_failure_siblings_complete(self) -> None:
        """When one agent fails, siblings should still complete."""
        from clef_server.orchestrator import ComposeOrchestrator

        orch = object.__new__(ComposeOrchestrator)

        async def succeed():
            return {"result": "ok"}

        async def fail():
            raise RuntimeError("agent crashed")

        # _run_agent_batch should use return_exceptions=True
        calls = [
            {"agent": "a", "_coro": succeed()},
            {"agent": "b", "_coro": fail()},
            {"agent": "c", "_coro": succeed()},
        ]
        results = await orch._run_agent_batch_raw([succeed(), fail(), succeed()])

        assert len(results) == 3
        assert results[0] == {"result": "ok"}
        assert isinstance(results[1], Exception)
        assert results[2] == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_all_succeed_results_in_order(self) -> None:
        """Results returned in original call order."""
        from clef_server.orchestrator import ComposeOrchestrator

        async def delayed(val, delay):
            await asyncio.sleep(delay)
            return val

        orch = object.__new__(ComposeOrchestrator)
        results = await orch._run_agent_batch_raw([
            delayed("first", 0.02),
            delayed("second", 0.01),  # finishes before first
            delayed("third", 0.0),
        ])

        assert results == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_empty_calls_returns_empty(self) -> None:
        from clef_server.orchestrator import ComposeOrchestrator

        orch = object.__new__(ComposeOrchestrator)
        results = await orch._run_agent_batch_raw([])
        assert results == []


# ══════════════════════════════════════════════════════════════════════════════
# 改进 2: Microcompact — compress tool output to pass/fail summary
# ══════════════════════════════════════════════════════════════════════════════


class TestMicrocompact:
    """Test _microcompact_messages compresses tool output."""

    def test_compresses_validate_abc_output(self) -> None:
        from clef_server.orchestrator import ComposeOrchestrator

        orch = object.__new__(ComposeOrchestrator)
        messages = [
            {
                "role": "tool",
                "name": "validate_abc",
                "content": json.dumps({
                    "report": {"is_valid": True},
                    "has_failures": False,
                    "issues": [],
                }),
            },
        ]
        result = orch._microcompact_messages(messages)
        assert len(result) == 1
        parsed = json.loads(result[0]["content"])
        assert parsed["tool"] == "validate_abc"
        assert parsed["pass"] is True
        assert parsed["issues_count"] == 0

    def test_compresses_abc_lint_output(self) -> None:
        from clef_server.orchestrator import ComposeOrchestrator

        orch = object.__new__(ComposeOrchestrator)
        messages = [
            {
                "role": "tool",
                "name": "abc_lint",
                "content": json.dumps({
                    "key": "C",
                    "pass": False,
                    "issues": [
                        {"rule": "double_barline", "severity": "WARN", "description": "double barline"},
                        {"rule": "duration", "severity": "FAIL", "description": "bar 3 incomplete"},
                    ],
                    "count": 2,
                }),
            },
        ]
        result = orch._microcompact_messages(messages)
        parsed = json.loads(result[0]["content"])
        assert parsed["tool"] == "abc_lint"
        assert parsed["pass"] is False
        assert parsed["issues_count"] == 2
        assert "fail_items" in parsed
        assert len(parsed["fail_items"]) == 1

    def test_preserves_fail_severity_items(self) -> None:
        from clef_server.orchestrator import ComposeOrchestrator

        orch = object.__new__(ComposeOrchestrator)
        messages = [
            {
                "role": "tool",
                "name": "validate_abc",
                "content": json.dumps({
                    "report": {"is_valid": False},
                    "has_failures": True,
                    "issues": [
                        {"check": "duration", "severity": "FAIL", "voice": "V:1"},
                        {"check": "range", "severity": "WARN", "voice": "V:2"},
                    ],
                }),
            },
        ]
        result = orch._microcompact_messages(messages)
        parsed = json.loads(result[0]["content"])
        assert parsed["has_failures"] is True
        assert "duration" in parsed["fail_items"]

    def test_non_compressible_tool_unchanged(self) -> None:
        from clef_server.orchestrator import ComposeOrchestrator

        orch = object.__new__(ComposeOrchestrator)
        messages = [
            {
                "role": "tool",
                "name": "write_file",
                "content": json.dumps({"path": "/tmp/test.txt"}),
            },
        ]
        result = orch._microcompact_messages(messages)
        assert result == messages

    def test_malformed_json_passed_through(self) -> None:
        from clef_server.orchestrator import ComposeOrchestrator

        orch = object.__new__(ComposeOrchestrator)
        messages = [
            {"role": "tool", "name": "validate_abc", "content": "not json"},
        ]
        result = orch._microcompact_messages(messages)
        assert result == messages

    def test_empty_messages_returns_empty(self) -> None:
        from clef_server.orchestrator import ComposeOrchestrator

        orch = object.__new__(ComposeOrchestrator)
        result = orch._microcompact_messages([])
        assert result == []

    def test_non_tool_messages_unchanged(self) -> None:
        from clef_server.orchestrator import ComposeOrchestrator

        orch = object.__new__(ComposeOrchestrator)
        messages = [
            {"role": "system", "content": "plan.json unchanged"},
            {"role": "user", "content": "make it better"},
        ]
        result = orch._microcompact_messages(messages)
        assert result == messages


# ══════════════════════════════════════════════════════════════════════════════
# 改进 6: File change cache — detect unchanged files across iterations
# ══════════════════════════════════════════════════════════════════════════════


class TestFileCache:
    """Test _FileCache for cross-iteration file change detection."""

    def test_first_read_returns_none(self, tmp_path: Path) -> None:
        from clef_server.orchestrator import _FileCache

        cache = _FileCache()
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")

        # First read: no cache, returns None (caller should process)
        result = cache.get_if_unchanged(str(f))
        assert result is None

    def test_second_read_returns_cached_content(self, tmp_path: Path) -> None:
        from clef_server.orchestrator import _FileCache

        cache = _FileCache()
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")

        cache.get_if_unchanged(str(f))  # populate cache
        result = cache.get_if_unchanged(str(f))  # second read
        assert result == "hello"

    def test_modified_file_returns_none(self, tmp_path: Path) -> None:
        from clef_server.orchestrator import _FileCache

        cache = _FileCache()
        f = tmp_path / "test.txt"
        f.write_text("v1", encoding="utf-8")

        cache.get_if_unchanged(str(f))  # cache v1
        f.write_text("v2", encoding="utf-8")  # modify
        result = cache.get_if_unchanged(str(f))
        assert result is None  # changed, must reprocess

    def test_invalidate_clears_cache(self, tmp_path: Path) -> None:
        from clef_server.orchestrator import _FileCache

        cache = _FileCache()
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")

        cache.get_if_unchanged(str(f))
        cache.invalidate(str(f))
        result = cache.get_if_unchanged(str(f))
        assert result is None  # invalidated

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        from clef_server.orchestrator import _FileCache

        cache = _FileCache()
        result = cache.get_if_unchanged(str(tmp_path / "nonexistent.txt"))
        assert result is None
