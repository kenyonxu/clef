"""Tests for tools.py -- AF @tool wrappers around existing Python scripts."""

import json
from pathlib import Path

import pytest
from agent_framework import FunctionTool

from clef_server.tools import (
    TOOLS_REGISTRY,
    _AGENT_TOOL_MAP,
    abc_lint,
    abc_to_midi,
    fix_measure_duration,
    get_tool_schemas,
    get_tools_for_agent,
    inject_expression,
    merge_abc,
    read_file,
    snapshot,
    validate_abc,
    write_file,
)


# ── read_file / write_file ────────────────────────────────────────────────


class TestReadFile:
    def test_reads_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        result = read_file(str(f), workdir=str(tmp_path))
        assert result == "hello world"

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="File not found"):
            read_file(str(tmp_path / "nonexistent.txt"), workdir=str(tmp_path))

    def test_reads_unicode_content(self, tmp_path: Path) -> None:
        f = tmp_path / "unicode.txt"
        content = "MIDI channel 1 \u4e2d\u6587"
        f.write_text(content, encoding="utf-8")
        assert read_file(str(f), workdir=str(tmp_path)) == content


class TestWriteFile:
    def test_writes_file(self, tmp_path: Path) -> None:
        f = tmp_path / "subdir" / "out.txt"
        result = write_file(str(f), "content", workdir=str(tmp_path))
        assert result["path"] == str(f)
        assert f.read_text(encoding="utf-8") == "content"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        f = tmp_path / "a" / "b" / "c" / "file.txt"
        write_file(str(f), "nested", workdir=str(tmp_path))
        assert f.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "overwrite.txt"
        f.write_text("old", encoding="utf-8")
        write_file(str(f), "new", workdir=str(tmp_path))
        assert f.read_text(encoding="utf-8") == "new"


# ── TOOLS_REGISTRY ────────────────────────────────────────────────────────


class TestToolsRegistry:
    def test_has_all_nine_tools(self) -> None:
        expected = {
            "read_file", "write_file", "validate_abc",
            "abc_to_midi", "abc_lint", "merge_abc",
            "inject_expression", "snapshot", "fix_measure_duration",
        }
        assert set(TOOLS_REGISTRY.keys()) == expected

    def test_all_values_are_callable(self) -> None:
        for name, func in TOOLS_REGISTRY.items():
            assert callable(func), f"{name} is not callable"

    def test_all_tools_have_is_tool_attribute(self) -> None:
        for name, func in TOOLS_REGISTRY.items():
            assert isinstance(func, FunctionTool), f"{name} is not a FunctionTool"


# ── get_tools_for_agent ──────────────────────────────────────────────────


class TestGetToolsForAgent:
    def test_clef_composer_tools(self) -> None:
        tools = get_tools_for_agent("clef-composer")
        names = {t.name for t in tools}
        assert names == {"read_file", "write_file", "validate_abc", "abc_lint"}

    def test_clef_harmonist_tools(self) -> None:
        tools = get_tools_for_agent("clef-harmonist")
        names = {t.name for t in tools}
        assert names == {"read_file", "write_file", "validate_abc", "abc_lint"}

    def test_clef_reviewer_no_write(self) -> None:
        tools = get_tools_for_agent("clef-reviewer")
        names = {t.name for t in tools}
        assert "write_file" not in names
        assert "read_file" in names
        assert "validate_abc" in names

    def test_clef_revision_read_write_only(self) -> None:
        tools = get_tools_for_agent("clef-revision")
        names = {t.name for t in tools}
        assert names == {"read_file", "write_file"}

    def test_clef_orchestrator_tools(self) -> None:
        tools = get_tools_for_agent("clef-orchestrator")
        names = {t.name for t in tools}
        assert "abc_to_midi" in names
        assert "inject_expression" in names

    def test_clef_repair_tools(self) -> None:
        tools = get_tools_for_agent("clef-repair")
        names = {t.name for t in tools}
        assert names == {"read_file", "write_file", "abc_lint", "fix_measure_duration"}

    def test_unknown_agent_returns_empty(self) -> None:
        tools = get_tools_for_agent("nonexistent-agent")
        assert tools == []


# ── abc_lint ──────────────────────────────────────────────────────────────


class TestAbcLint:
    def test_clean_abc_passes(self, sample_abc: str) -> None:
        result = abc_lint(sample_abc)
        assert "issues" in result
        assert isinstance(result["count"], int)

    def test_detects_double_barline(self) -> None:
        abc = """X:1
T:Test
M:4/4
L:1/4
Q:1/4=120
K:C
V:1
C E G || c |"""
        result = abc_lint(abc)
        assert result["count"] >= 1
        rules = [i.get("rule") for i in result["issues"]]
        assert "double_barline" in rules

    def test_with_plan_path(self, tmp_path: Path, sample_abc: str, sample_plan: dict) -> None:
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(sample_plan), encoding="utf-8")
        result = abc_lint(sample_abc, plan_path=str(plan_file))
        assert "issues" in result

    def test_returns_zero_count_on_valid_input(self) -> None:
        minimal = "X:1\nT:T\nM:4/4\nL:1/8\nQ:1/4=120\nK:C\nV:1\nC2 E2 G2 c2 |"
        result = abc_lint(minimal)
        assert result["count"] == 0


# ── merge_abc ─────────────────────────────────────────────────────────────


class TestMergeAbc:
    def test_merges_voice_fragments(
        self, tmp_path: Path, sample_plan: dict
    ) -> None:
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(sample_plan), encoding="utf-8")
        output_file = tmp_path / "score.abc"

        fragments = {
            "V:1": '"C" C2 E2 G2 c2 |',
            "V:2": 'C,2 E,2 G,2 C2 |',
        }

        result = merge_abc(str(plan_file), fragments, str(output_file))
        assert "output" in result
        assert output_file.exists()

        content = output_file.read_text(encoding="utf-8")
        assert "V:1" in content
        assert "V:2" in content

    def test_merge_with_orchestration(self, tmp_path: Path) -> None:
        plan = {
            "title": "Orch Test",
            "key": "C",
            "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {
                "melody": {"channel": 0, "instrument": 0, "name": "Piano"},
                "harmony": {"channel": 1, "instrument": 0, "name": "Piano"},
            },
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan), encoding="utf-8")
        output_file = tmp_path / "merged.abc"

        fragments = {
            "V:1": "C2 E2 G2 c2 |",
            "V:2": "C,2 E,2 G,2 C2 |",
        }

        result = merge_abc(str(plan_file), fragments, str(output_file))
        assert "output" in result
        content = output_file.read_text(encoding="utf-8")
        assert "%%MIDI channel 0" in content
        assert "%%MIDI channel 1" in content


# ── validate_abc (dependency-optional) ────────────────────────────────────


class TestValidateAbc:
    def test_returns_error_without_music21(
        self, tmp_path: Path, sample_abc: str, sample_plan: dict
    ) -> None:
        abc_file = tmp_path / "test.abc"
        abc_file.write_text(sample_abc, encoding="utf-8")
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(sample_plan), encoding="utf-8")
        output_file = tmp_path / "report.json"

        result = validate_abc(str(abc_file), str(plan_file), str(output_file))

        # If music21 IS installed, this will succeed; otherwise it returns an error dict
        assert isinstance(result, dict)
        if "error" in result:
            assert result["has_failures"] is True
            assert "music21" in result["error"]
        else:
            assert "report" in result

    def test_returns_error_for_missing_file(self) -> None:
        result = validate_abc("/nonexistent/file.abc", "/nonexistent/plan.json", "/tmp/out.json")
        assert "error" in result
        assert result["has_failures"] is True


# ── abc_to_midi (dependency-optional) ────────────────────────────────────


class TestAbcToMidi:
    def test_returns_error_without_mido(self, tmp_path: Path, sample_abc: str) -> None:
        abc_file = tmp_path / "test.abc"
        abc_file.write_text(sample_abc, encoding="utf-8")
        output_file = tmp_path / "test.mid"

        result = abc_to_midi(str(abc_file), str(output_file))

        assert isinstance(result, dict)
        if "error" in result:
            assert "mido" in result["error"].lower()
        else:
            assert "output" in result
            assert output_file.exists()

    def test_returns_error_for_missing_input(self) -> None:
        result = abc_to_midi("/nonexistent/file.abc", "/tmp/out.mid")
        assert "error" in result


# ── inject_expression (dependency-optional) ──────────────────────────────


class TestInjectExpression:
    def test_returns_error_for_missing_files(self) -> None:
        result = inject_expression(
            "/nonexistent/base.mid",
            "/nonexistent/plan.json",
            "/tmp/out.mid",
        )
        assert "error" in result


# ── snapshot (zero dependencies) ──────────────────────────────────────────


class TestSnapshot:
    def test_snapshot_creates_log(
        self, tmp_path: Path, sample_plan: dict
    ) -> None:
        workdir = tmp_path / ".clef-work"
        workdir.mkdir()
        (workdir / "plan.json").write_text(json.dumps(sample_plan), encoding="utf-8")
        output_file = workdir / "snapshot.abc"

        result = snapshot(step="1a", output=str(output_file), note="Initial draft")
        assert "snapshot" in result
        assert "exit_code" in result
        assert result["exit_code"] == 0

    def test_snapshot_creates_backup(self, tmp_path: Path, sample_plan: dict) -> None:
        workdir = tmp_path / ".clef-work"
        workdir.mkdir()
        (workdir / "plan.json").write_text(json.dumps(sample_plan), encoding="utf-8")
        score = workdir / "score.abc"
        score.write_text("X:1\nT:Test\nK:C\nV:1\nC |", encoding="utf-8")
        output_file = workdir / "snapshot.abc"

        result = snapshot(step="2", output=str(output_file), note="Step 2")
        assert result["exit_code"] == 0

        # Verify backup was created in history/
        history_dir = workdir / "history"
        assert history_dir.exists()
        backups = list(history_dir.glob("score_v*.abc"))
        assert len(backups) >= 1


# ── get_tool_schemas ────────────────────────────────────────────────────


class TestGetToolSchemas:
    def test_get_tool_schemas_composer(self) -> None:
        schemas = get_tool_schemas("clef-composer")
        assert len(schemas) == 4
        names = {s["function"]["name"] for s in schemas}
        assert names == {"read_file", "write_file", "validate_abc", "abc_lint"}

    def test_get_tool_schemas_structure(self) -> None:
        schemas = get_tool_schemas("clef-composer")
        for schema in schemas:
            assert schema["type"] == "function"
            func = schema["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            params = func["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
            assert "required" in params

    def test_get_tool_schemas_unknown_agent(self) -> None:
        schemas = get_tool_schemas("nonexistent-agent")
        assert schemas == []


# === fix_measure_duration tests ===


class TestFixMeasureDuration:
    def test_correct_measure_unchanged(self):
        """Correct measures should not be modified."""
        abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 f2 |"
        result = fix_measure_duration(abc)
        assert result["passed"] is True
        assert result["fixes"] == []
        assert result["abc"] == abc

    def test_short_by_one_extends_last_note(self):
        """Missing 1 unit: extend last note."""
        # 7/8 units: c2(2) + d2(2) + e2(2) + f(1) = 7
        abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 f |"
        result = fix_measure_duration(abc)
        assert result["passed"] is False
        assert len(result["fixes"]) == 1
        assert "f2" in result["abc"]
        assert result["fixes"][0]["measure"] == 1
        assert result["fixes"][0]["action"] == "extend"

    def test_long_by_one_shortens_last_note(self):
        """Extra 1 unit: shorten or remove last note."""
        # 9/8 units: c2(2) + d2(2) + e2(2) + f2(2) + g(1) = 9
        abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 f2 g |"
        result = fix_measure_duration(abc)
        assert result["passed"] is False
        assert len(result["fixes"]) == 1

    def test_multiple_measures_only_fixes_wrong(self):
        """Multiple measures: only incorrect ones are fixed."""
        # M1: 8 units (correct), M2: 7 units (short by 1)
        abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 f2 | c2 d2 e2 f |"
        result = fix_measure_duration(abc)
        assert result["passed"] is False
        assert len(result["fixes"]) == 1
        assert result["fixes"][0]["measure"] == 2

    def test_large_deviation_skipped(self):
        """Off by >2 units: skip (no fix applied)."""
        # 5/8 units -- off by 3
        abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e |"
        result = fix_measure_duration(abc)
        assert result["passed"] is False
        assert len(result["fixes"]) == 1
        assert result["fixes"][0].get("skipped") is True

    def test_rest_extension(self):
        """Missing unit: extend rest."""
        # 7/8 units: c2(2) + d2(2) + e2(2) + z(1) = 7
        abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 z |"
        result = fix_measure_duration(abc)
        assert result["passed"] is False
        assert len(result["fixes"]) == 1
        assert "z2" in result["abc"]

    def test_chord_counted_as_single_event(self):
        """Chord [CEG]2 counts as one event with duration 2, not three notes."""
        # [CEG]2(2) + [DFA]2(2) + [CEG]2(2) + [DFA]2(2) = 8 (correct)
        abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\n[CEG]2 [DFA]2 [CEG]2 [DFA]2 |"
        result = fix_measure_duration(abc)
        assert result["passed"] is True
        assert result["fixes"] == []

    def test_tuplet_counted_correctly(self):
        """Triplet (3c d e should count as divided by 3, not raw sum."""
        # (3e f g = triplet: 3 notes in 2 units' time. With duration 1 each = 3*2/3 = 2
        # Total: c2(2) + d2(2) + triplet(2) + f2(2) = 8
        abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 (3e f g f2 |"
        result = fix_measure_duration(abc)
        assert result["passed"] is True

    def test_default_L_is_quarter(self):
        """When L: not specified, default is 1/4 (ABC standard)."""
        # No L: header, M:4/4 -> target = 4 * 4 / 4 = 4 units
        # c(1) + d(1) + e(1) + f(1) = 4 (correct)
        abc = "X:1\nM:4/4\nK:C\nV:1\nc d e f |"
        result = fix_measure_duration(abc)
        assert result["passed"] is True

    def test_target_per_measure_override(self):
        """Explicit target_per_measure overrides auto-detect."""
        abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 |"
        result = fix_measure_duration(abc, target_per_measure=4.0)
        assert result["passed"] is True

    def test_measures_checked_count(self):
        """measures_checked reflects actual number of measures."""
        abc = "X:1\nM:4/4\nL:1/8\nK:C\nV:1\nc2 d2 e2 f2 | c2 d2 e2 f2 | c2 d2 e2 f2 |"
        result = fix_measure_duration(abc)
        assert result["measures_checked"] == 3
