"""Tests for response_parser module."""

import json
import pytest
from pathlib import Path

from clef_server.response_parser import (
    extract_abc,
    extract_json,
    extract_rhythm,
    is_placeholder,
    looks_like_abc,
    normalize_review,
    strip_tool_markers,
)


# === looks_like_abc ===

class TestLooksLikeAbc:
    def test_valid_abc_with_headers(self):
        text = "X:1\nT:Test\nM:4/4\nK:C\n|: C D E F :|"
        assert looks_like_abc(text) is True

    def test_valid_abc_with_voice(self):
        text = "V:1\nC D E F | G A B c |"
        assert looks_like_abc(text) is True

    def test_valid_abc_with_note_letters(self):
        text = "X:1\nM:4/4\nK:C\nCDEF GABc"
        assert looks_like_abc(text) is True

    def test_plain_text_rejected(self):
        text = "Here is some music description for you"
        assert looks_like_abc(text) is False

    def test_empty_string_rejected(self):
        assert looks_like_abc("") is False

    def test_whitespace_only_rejected(self):
        assert looks_like_abc("   \n  ") is False

    def test_json_rejected(self):
        text = '{"verdict": "pass", "scores": {"melody": 7}}'
        assert looks_like_abc(text) is False


# === extract_abc ===

class TestExtractAbc:
    def test_extract_from_markdown_fence(self):
        text = 'Here is the melody:\n```abc\nX:1\nM:4/4\nK:C\nC D E F |\n```'
        result = extract_abc(text)
        assert "X:1" in result
        assert "K:C" in result

    def test_extract_from_markdown_fence_no_lang(self):
        text = '```\nX:1\nM:4/4\nK:C\nC D E F |\n```'
        result = extract_abc(text)
        assert "X:1" in result

    def test_extract_inline_abc(self):
        text = "X:1\nM:4/4\nK:C\nC D E F | G A B c |"
        result = extract_abc(text)
        assert "X:1" in result
        assert "K:C" in result

    def test_no_abc_returns_empty(self):
        text = "This is just some prose about music theory."
        result = extract_abc(text)
        assert result == ""

    def test_raw_content_object_returns_empty(self):
        text = "Content(type='text', text='hello')"
        result = extract_abc(text)
        assert result == ""

    def test_tool_call_syntax_stripped_returns_empty_when_no_abc_after_strip(self):
        """Tool markers stripped but remaining text doesn't start with ABC header before fence."""
        text = '<|DSML|>tool_call{"name":"foo"}<|DSML|>\n```abc\nX:1\nM:4/4\nK:C\nC D |\n```'
        result = extract_abc(text)
        # After stripping DSML, looks_like_abc is checked on the full remaining text.
        # It starts with ````abc\n` which doesn't match any ABC header, so returns empty.
        assert result == ""

    def test_tool_call_syntax_stripped_preserves_fenced_abc(self):
        """Tool markers before a fenced ABC block that starts with ABC header inside."""
        text = '<|DSML|>tool_call{}<|DSML|>\nX:1\nM:4/4\nK:C\nC D E F |\n```'
        result = extract_abc(text)
        assert "X:1" in result


# === is_placeholder ===

class TestIsPlaceholder:
    def test_placeholder_keyword(self):
        text = "[placeholder] some text"
        assert is_placeholder(text) is True

    def test_placeholder_keyword_uppercase(self):
        text = "PLACEHOLDER"
        assert is_placeholder(text) is True

    def test_too_short(self):
        text = "X:1"
        assert is_placeholder(text) is True

    def test_no_music_characters_but_has_note_letters(self):
        """Text with 'e' or 'a' passes the music-char check, but fails the barline check."""
        text = "This is some text without barlines"
        # 'e' and 'a' are in the note-letter set, so is_placeholder returns False
        assert is_placeholder(text) is False

    def test_no_music_or_barline_characters(self):
        """Text without any note letters or barlines is a placeholder."""
        text = "ABCD 1234 ----"
        # No |, a, b, c, d, e, f, g, ' in text — but 'a','b','c','d' are present
        # Actually a,b,c,d ARE note letters, so this passes too
        text = "XKLMNOP 1234 ----"
        assert is_placeholder(text) is True

    def test_real_music_rejected(self):
        text = "X:1\nM:4/4\nK:C\nC D E F | G A B c |"
        assert is_placeholder(text) is False

    def test_real_music_with_barline(self):
        text = "V:1\n| C D E F | G A B c |"
        assert is_placeholder(text) is False


# === strip_tool_markers ===

class TestStripToolMarkers:
    def test_remove_dsml_block(self):
        text = "before\n<|DSML|>tool_call{\"name\": \"x\"}<|DSML|>\nafter"
        result = strip_tool_markers(text)
        assert "<|DSML|>" not in result
        assert "before" in result
        assert "after" in result

    def test_remove_function_calls_block(self):
        text = "start\n<function_calls>\n<invoke name=\"foo\"/>\n</function_calls>\nend"
        result = strip_tool_markers(text)
        assert "<function_calls>" not in result
        assert "start" in result
        assert "end" in result

    def test_remove_invoke_line(self):
        text = "music here\n<invoke name=\"abc_to_midi\"/>\nmore music"
        result = strip_tool_markers(text)
        assert "<invoke" not in result
        assert "music here" in result

    def test_remove_tool_call_line(self):
        text = "X:1\ntool_call{\"name\":\"foo\"}\nK:C"
        result = strip_tool_markers(text)
        assert "tool_call" not in result

    def test_remove_FunctionCall_line(self):
        text = "X:1\nFunctionCall(name=\"bar\")\nK:C"
        result = strip_tool_markers(text)
        assert "FunctionCall" not in result

    def test_clean_text_unchanged(self):
        text = "X:1\nM:4/4\nK:C\nC D E F |"
        assert strip_tool_markers(text) == text.strip()

    def test_collapse_multiple_blank_lines(self):
        text = "X:1\n\n\n\n\nK:C"
        result = strip_tool_markers(text)
        assert "\n\n\n" not in result


# === extract_json ===

class TestExtractJson:
    def test_from_markdown_fence(self):
        payload = {"verdict": "pass", "overall_score": 8}
        text = f"Here is the review:\n```json\n{json.dumps(payload)}\n```"
        result = extract_json(text)
        assert result["verdict"] == "pass"
        assert result["overall_score"] == 8

    def test_bare_json(self):
        payload = {"verdict": "revise", "overall_score": 5}
        text = json.dumps(payload)
        result = extract_json(text)
        assert result["verdict"] == "revise"

    def test_invalid_json_returns_revise(self):
        text = "This is not JSON at all"
        result = extract_json(text)
        assert result == {"verdict": "revise"}

    def test_tool_markers_stripped_then_parsed(self):
        payload = {"verdict": "pass"}
        text = f'<|DSML|>tool_call{{}}<|DSML|>\n```json\n{json.dumps(payload)}\n```'
        result = extract_json(text)
        assert result["verdict"] == "pass"

    def test_invalid_json_after_strip_returns_revise(self):
        text = "<|DSML|>tool_call{}<|DSML|>\nnot json"
        result = extract_json(text)
        assert result == {"verdict": "revise"}


# === extract_rhythm ===

class TestExtractRhythm:
    def test_from_rhythm_fence(self):
        text = "```rhythm\n| 1 2 3 4 | 1 2 3 4 |\n```"
        result = extract_rhythm(text)
        assert "1 2 3 4" in result

    def test_from_generic_fence(self):
        text = "```\n| 1 2 | 3 4 |\n```"
        result = extract_rhythm(text)
        assert "1 2" in result

    def test_fallback_bar_line_with_digits(self):
        text = "Here is the rhythm:\n| 1 2 3 4 | 1 2 3 4 |\nDone"
        result = extract_rhythm(text)
        assert "1 2 3 4" in result

    def test_no_rhythm_returns_empty(self):
        text = "This has no rhythm pattern at all"
        result = extract_rhythm(text)
        assert result == ""

    def test_tool_markers_stripped(self):
        text = '<|DSML|>tool_call{}<|DSML|>\n```rhythm\n| 1 2 3 4 |\n```'
        result = extract_rhythm(text)
        assert "1 2 3 4" in result


# === normalize_review ===

class TestNormalizeReview:
    def test_nested_dimensions(self):
        raw = {
            "verdict": "pass",
            "dimensions": {
                "melody": {"score": 8, "issues": ["low energy"]},
                "harmony": {"score": 7},
            },
            "overall_score": 7.5,
        }
        result = normalize_review(raw)
        assert result["verdict"] == "pass"
        assert result["scores"]["melody"] == 8
        assert result["scores"]["harmony"] == 7
        assert result["overall_score"] == 7.5
        assert len(result["issues"]) == 1
        assert result["issues"][0] == "low energy"

    def test_flat_scores_fallback(self):
        raw = {"verdict": "pass", "scores": {"melody": 6, "harmony": 5}}
        result = normalize_review(raw)
        assert result["scores"]["melody"] == 6
        assert result["scores"]["harmony"] == 5

    def test_summary_from_overall_score(self):
        raw = {"overall_score": 8, "dimensions": {"melody": {"score": 8}}}
        result = normalize_review(raw)
        assert "8/10" in result["summary"]

    def test_summary_derived_from_avg_when_no_overall(self):
        raw = {"dimensions": {"melody": {"score": 6}, "harmony": {"score": 8}}}
        result = normalize_review(raw)
        assert "7.0/10" in result["summary"]

    def test_explicit_summary_preserved(self):
        raw = {"summary": "Great work!", "dimensions": {"melody": {"score": 9}}}
        result = normalize_review(raw)
        assert result["summary"] == "Great work!"

    def test_issues_as_dicts(self):
        raw = {
            "dimensions": {
                "melody": {
                    "score": 5,
                    "issues": [{"description": "repetitive"}, "too short"],
                }
            }
        }
        result = normalize_review(raw)
        assert "repetitive" in result["issues"]
        assert "too short" in result["issues"]

    def test_empty_input(self):
        result = normalize_review({})
        assert result["verdict"] == "pass"
        assert result["scores"] == {}
        assert result["overall_score"] == 0

    def test_dimension_with_numeric_value(self):
        raw = {"dimensions": {"melody": 8, "harmony": 7}}
        result = normalize_review(raw)
        assert result["scores"]["melody"] == 8
        assert result["scores"]["harmony"] == 7
