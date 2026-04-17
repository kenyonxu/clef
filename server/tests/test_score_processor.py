"""Tests for score_processor module -- pure ABC/MIDI score manipulation functions."""

import json
from pathlib import Path

import pytest

from clef_server.score_processor import (
    apply_duration_constraint,
    calculate_demo_bars,
    count_bars,
    inject_midi_programs,
    parse_voice_blocks,
    store_fragment,
    stamp_agent_meta,
    trim_trailing_rests,
    truncate_score_per_voice,
    truncate_to_bars,
    truncate_voice_lines,
)


# ---------------------------------------------------------------------------
# stamp_agent_meta
# ---------------------------------------------------------------------------

class TestStampAgentMeta:
    def test_adds_meta_comment(self):
        result = stamp_agent_meta("C D E F|", "clef-composer", "V:1", 1)
        assert result.startswith("% ClefMeta:")
        assert "clef-composer" in result
        assert "V:1" in result
        assert "C D E F|" in result

    def test_preserves_content(self):
        content = "C D E F|\nG A B c|"
        result = stamp_agent_meta(content, "agent", "V:2", 0)
        lines = result.strip().split("\n")
        # First line is meta, rest is original
        assert lines[-2] == "C D E F|"
        assert lines[-1] == "G A B c|"


# ---------------------------------------------------------------------------
# inject_midi_programs
# ---------------------------------------------------------------------------

class TestInjectMidiPrograms:
    def test_injects_program_for_voice(self, tmp_path):
        score = tmp_path / "score.abc"
        score.write_text("V:1\nC D E F|\n", encoding="utf-8")
        plan = {"orchestration": {"melody": {"midi_program": 0}}}
        inject_midi_programs(score, plan)
        text = score.read_text(encoding="utf-8")
        assert "%%MIDI program 0" in text

    def test_skips_existing_program(self, tmp_path):
        score = tmp_path / "score.abc"
        score.write_text("V:1\n%%MIDI program 1\nC D E F|\n", encoding="utf-8")
        plan = {"orchestration": {"melody": {"midi_program": 0}}}
        inject_midi_programs(score, plan)
        text = score.read_text(encoding="utf-8")
        # Old directive removed, new one injected
        assert "%%MIDI program 0" in text
        assert text.count("%%MIDI program") == 1

    def test_no_injection_without_midi_program(self, tmp_path):
        score = tmp_path / "score.abc"
        original = "V:1\nC D E F|\n"
        score.write_text(original, encoding="utf-8")
        plan = {"orchestration": {"melody": {}}}
        inject_midi_programs(score, plan)
        assert score.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# apply_duration_constraint
# ---------------------------------------------------------------------------

class TestApplyDurationConstraint:
    def test_seconds_pattern(self):
        plan = {"bpm": 120, "time_signature": "4/4", "total_bars": 32, "sections": [{"measures": 32}]}
        result = apply_duration_constraint(plan, "写一首30秒的音乐")
        assert result["total_bars"] != 32
        # 30s at 120bpm 4/4 = 15 bars -> clamped to 15
        assert result["total_bars"] == 15

    def test_minutes_pattern(self):
        plan = {"bpm": 120, "time_signature": "4/4", "total_bars": 32, "sections": [{"measures": 32}]}
        result = apply_duration_constraint(plan, "1分钟")
        # 60s at 120bpm 4/4 = 30 bars
        assert result["total_bars"] == 30

    def test_no_duration_in_prompt(self):
        plan = {"bpm": 120, "time_signature": "4/4", "total_bars": 32, "sections": [{"measures": 32}]}
        result = apply_duration_constraint(plan, "写一首欢快的曲子")
        assert result["total_bars"] == 32

    def test_minimum_8_bars(self):
        plan = {"bpm": 120, "time_signature": "4/4", "total_bars": 32, "sections": [{"measures": 32}]}
        result = apply_duration_constraint(plan, "3秒")
        assert result["total_bars"] >= 8

    def test_sections_redistributed(self):
        plan = {
            "bpm": 120,
            "time_signature": "4/4",
            "total_bars": 32,
            "sections": [{"measures": 16}, {"measures": 16}],
        }
        result = apply_duration_constraint(plan, "30秒")
        new_total = sum(s["measures"] for s in result["sections"])
        assert new_total == result["total_bars"]


# ---------------------------------------------------------------------------
# trim_trailing_rests
# ---------------------------------------------------------------------------

class TestTrimTrailingRests:
    def test_removes_trailing_rests(self):
        abc = "C D E F|\nz2 |\nz4 |"
        result = trim_trailing_rests(abc)
        assert result == "C D E F|"

    def test_preserves_notes(self):
        abc = "C D E F|"
        result = trim_trailing_rests(abc)
        assert result == "C D E F|"

    def test_preserves_mixed_ending(self):
        abc = "C D E F|\nG A B c|\nz2 |"
        result = trim_trailing_rests(abc)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert "G A B c" in lines[1]

    def test_empty_input(self):
        assert trim_trailing_rests("") == ""

    def test_all_rests(self):
        abc = "z2 |\nz4 |\nz2 |"
        result = trim_trailing_rests(abc)
        assert result == ""


# ---------------------------------------------------------------------------
# calculate_demo_bars
# ---------------------------------------------------------------------------

class TestCalculateDemoBars:
    def test_thirty_percent(self):
        # 100 * 0.3 = 30
        assert calculate_demo_bars(100) == 30

    def test_minimum_clamp(self):
        assert calculate_demo_bars(10) == 8  # 3 rounds to 8

    def test_maximum_clamp(self):
        # 300 * 0.3 = 90 -> clamped to 64
        assert calculate_demo_bars(300) == 64

    def test_zero_input(self):
        assert calculate_demo_bars(0) == 8

    def test_negative_input(self):
        assert calculate_demo_bars(-5) == 8


# ---------------------------------------------------------------------------
# parse_voice_blocks
# ---------------------------------------------------------------------------

class TestParseVoiceBlocks:
    def test_single_voice(self):
        score = "V:1\nC D E F|\nG A B c|"
        blocks = parse_voice_blocks(score)
        assert "V:1" in blocks
        assert "C D E F" in blocks["V:1"]

    def test_two_voices(self):
        score = "V:1\nC D E F|\nV:2\nC, E, G,|"
        blocks = parse_voice_blocks(score)
        assert len(blocks) == 2
        assert "V:1" in blocks
        assert "V:2" in blocks
        assert "G," in blocks["V:2"]

    def test_four_voices(self):
        score = "V:1\nC D|\nV:2\nE G|\nV:3\nC,,|\nV:4\nz2|"
        blocks = parse_voice_blocks(score)
        assert len(blocks) == 4

    def test_empty_input(self):
        blocks = parse_voice_blocks("")
        assert blocks == {}

    def test_skips_header_lines(self):
        score = "X:1\nT:Test\nK:C\nV:1\nC D E F|"
        blocks = parse_voice_blocks(score)
        assert "V:1" in blocks
        # Header lines before first V: are discarded
        assert "X:1" not in blocks.get("V:1", "")


# ---------------------------------------------------------------------------
# count_bars
# ---------------------------------------------------------------------------

class TestCountBars:
    def test_simple_bars(self):
        abc = "C D E F|G A B c|"
        assert count_bars(abc) == 2

    def test_double_bars_excluded(self):
        abc = "C D E F||"
        assert count_bars(abc) == 0

    def test_repeat_start_excluded(self):
        abc = "|:C D E F|G A B c:|"
        assert count_bars(abc) == 1

    def test_double_bar_excluded(self):
        abc = "C D E F|G A B c||"
        # First | matches, || excluded
        assert count_bars(abc) == 1

    def test_comments_skipped(self):
        abc = "% this is a comment\nC D E F|"
        assert count_bars(abc) == 1

    def test_empty_input(self):
        assert count_bars("") == 0

    def test_no_bars(self):
        abc = "C D E F G A B c"
        assert count_bars(abc) == 0


# ---------------------------------------------------------------------------
# truncate_to_bars
# ---------------------------------------------------------------------------

class TestTruncateToBars:
    def test_truncates_correctly(self):
        abc = "C D E F|\nG A B c|\nC' B A G|"
        result = truncate_to_bars(abc, 2)
        assert count_bars(result) == 2

    def test_no_op_when_fewer_bars(self):
        abc = "C D E F|\nG A B c|"
        result = truncate_to_bars(abc, 5)
        assert count_bars(result) == 2

    def test_preserves_comments(self):
        abc = "% comment\nC D E F|\nG A B c|\nF E D C|"
        result = truncate_to_bars(abc, 1)
        assert "% comment" in result
        assert count_bars(result) == 1

    def test_empty_input(self):
        result = truncate_to_bars("", 4)
        assert result == ""


# ---------------------------------------------------------------------------
# truncate_voice_lines
# ---------------------------------------------------------------------------

class TestTruncateVoiceLines:
    def test_truncates_music_lines(self):
        lines = ["V:1", "C D E F|", "G A B c|", "F E D C|"]
        result = truncate_voice_lines(lines, 2)
        # V:1 kept + 2 bars
        assert len(result) == 3

    def test_keeps_voice_directive(self):
        lines = ["V:1", "C D E F|", "G A B c|"]
        result = truncate_voice_lines(lines, 1)
        assert result[0] == "V:1"

    def test_empty_lines(self):
        assert truncate_voice_lines([], 4) == []


# ---------------------------------------------------------------------------
# truncate_score_per_voice
# ---------------------------------------------------------------------------

class TestTruncateScorePerVoice:
    def test_truncates_each_voice(self):
        abc = (
            "X:1\nT:Test\nK:C\n"
            "V:1\nC D E F|G A B c|F E D C|B A G F|\n"
            "V:2\nC, E, G,|D, F, A,|B,, D, F,|G,, B, D,|"
        )
        result = truncate_score_per_voice(abc, 2)
        # Each voice should have 2 bars
        blocks = parse_voice_blocks(result)
        for voice, content in blocks.items():
            assert count_bars(content) == 2, f"{voice} has {count_bars(content)} bars"

    def test_preserves_headers(self):
        abc = "X:1\nT:Test\nK:C\nV:1\nC D E F|"
        result = truncate_score_per_voice(abc, 1)
        assert result.startswith("X:1\nT:Test\nK:C")


# ---------------------------------------------------------------------------
# store_fragment
# ---------------------------------------------------------------------------

class TestStoreFragment:
    def test_single_voice(self):
        fragments: dict[str, str] = {}
        parts: list[str] = []
        store_fragment(fragments, parts, "V:1", "C D E F|", round_num=1)
        assert "V:1" in fragments
        assert "C D E F" in fragments["V:1"]
        assert len(parts) == 1
        # Should have ClefMeta stamped
        assert "% ClefMeta:" in fragments["V:1"]

    def test_multi_voice_rhythm(self):
        fragments: dict[str, str] = {}
        parts: list[str] = []
        abc = "V:3\nC,, E,,|\nV:4\nz2 z2|"
        store_fragment(fragments, parts, "V:3+V:4", abc)
        assert "V:3" in fragments
        assert "V:4" in fragments
        assert "C,," in fragments["V:3"]
        assert "z2" in fragments["V:4"]

    def test_none_parts(self):
        fragments: dict[str, str] = {}
        store_fragment(fragments, None, "V:1", "C D E F|")
        assert "V:1" in fragments
