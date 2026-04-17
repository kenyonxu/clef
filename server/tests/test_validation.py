"""Tests for clef_server.validation module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clef_server.validation import (
    format_validation_feedback,
    run_validation,
    run_validation_from_abc,
)


# === format_validation_feedback ===


class TestFormatValidationFeedback:
    def test_empty_failures_returns_empty_string(self):
        result = format_validation_feedback([])
        assert result == ""

    def test_single_failure(self):
        failures = [{"category": "range", "voice": "V:1", "message": "Note A6 exceeds range"}]
        result = format_validation_feedback(failures)
        assert "VALIDATION FAILURES" in result
        assert "[range] V:1: Note A6 exceeds range" in result

    def test_multiple_failures(self):
        failures = [
            {"category": "range", "voice": "V:1", "message": "Note A6 exceeds range"},
            {"category": "duration", "voice": "V:2", "message": "Measure 5 duration mismatch"},
        ]
        result = format_validation_feedback(failures)
        assert "[range] V:1:" in result
        assert "[duration] V:2:" in result
        assert "Re-check every measure" in result

    def test_output_has_header_and_footer(self):
        failures = [{"category": "x", "voice": "V:1", "message": "m"}]
        result = format_validation_feedback(failures)
        lines = result.strip().split("\n")
        assert lines[0].startswith("VALIDATION FAILURES")
        assert lines[-1].startswith("You MUST fix")


# === run_validation ===


class TestRunValidation:
    @patch("clef_server.tools.validate_abc")
    def test_returns_empty_when_error(self, mock_validate, tmp_path):
        mock_validate.return_value = {"error": "script not found"}
        report_path = tmp_path / "report.json"
        result = run_validation(tmp_path / "score.abc", tmp_path / "plan.json", report_path)
        assert result == []

    @patch("clef_server.tools.validate_abc")
    def test_returns_empty_when_no_report_file(self, mock_validate, tmp_path):
        mock_validate.return_value = {"ok": True}
        report_path = tmp_path / "missing_report.json"
        result = run_validation(tmp_path / "score.abc", tmp_path / "plan.json", report_path)
        assert result == []

    @patch("clef_server.tools.validate_abc")
    def test_returns_real_fails_filtering_known_artifacts(self, mock_validate, tmp_path):
        mock_validate.return_value = {"ok": True}
        report_path = tmp_path / "report.json"
        report = {
            "fails": [
                {"category": "range", "voice": "V:1", "message": "too high"},
                {"category": "range", "voice": "V:2", "message": "ok", "known_artifact": True},
            ]
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        result = run_validation(tmp_path / "score.abc", tmp_path / "plan.json", report_path, session_id="test-123")
        assert len(result) == 1
        assert result[0]["voice"] == "V:1"

    @patch("clef_server.tools.validate_abc")
    def test_returns_empty_when_all_are_known_artifacts(self, mock_validate, tmp_path):
        mock_validate.return_value = {"ok": True}
        report_path = tmp_path / "report.json"
        report = {"fails": [{"category": "x", "voice": "V:1", "message": "m", "known_artifact": True}]}
        report_path.write_text(json.dumps(report), encoding="utf-8")
        result = run_validation(tmp_path / "score.abc", tmp_path / "plan.json", report_path)
        assert result == []


# === run_validation_from_abc ===


class TestRunValidationFromAbc:
    @patch("clef_server.tools.validate_abc")
    def test_returns_error_on_exception(self, mock_validate, tmp_path):
        mock_validate.side_effect = RuntimeError("boom")
        report_path = tmp_path / "report.json"
        result = run_validation_from_abc("X:1\nK:C\nC", tmp_path / "plan.json", report_path, tmp_path, voice_label="V:1")
        assert len(result) == 1
        assert result[0]["category"] == "validation_error"
        assert "boom" in result[0]["message"]

    @patch("clef_server.tools.validate_abc")
    def test_returns_error_on_tool_error_dict(self, mock_validate, tmp_path):
        mock_validate.return_value = {"error": "validate_abc not found"}
        report_path = tmp_path / "report.json"
        result = run_validation_from_abc("X:1\nK:C\nC", tmp_path / "plan.json", report_path, tmp_path)
        assert len(result) == 1
        assert result[0]["category"] == "validation_error"

    @patch("clef_server.tools.validate_abc")
    def test_reads_fails_from_report(self, mock_validate, tmp_path):
        mock_validate.return_value = {"ok": True}
        report_path = tmp_path / "report.json"
        report = {"fails": [{"category": "range", "voice": "V:1", "message": "bad note"}]}
        report_path.write_text(json.dumps(report), encoding="utf-8")
        result = run_validation_from_abc("X:1\nK:C\nC", tmp_path / "plan.json", report_path, tmp_path)
        assert len(result) == 1
        assert result[0]["category"] == "range"

    @patch("clef_server.tools.validate_abc")
    def test_returns_empty_when_no_report_file(self, mock_validate, tmp_path):
        mock_validate.return_value = {"ok": True}
        report_path = tmp_path / "missing.json"
        result = run_validation_from_abc("X:1\nK:C\nC", tmp_path / "plan.json", report_path, tmp_path)
        assert result == []

    @patch("clef_server.tools.validate_abc")
    def test_writes_abc_to_workdir(self, mock_validate, tmp_path):
        mock_validate.return_value = {"ok": True}
        report_path = tmp_path / "report.json"
        abc_text = "X:1\nK:C\nC D E"
        run_validation_from_abc(abc_text, tmp_path / "plan.json", report_path, tmp_path, voice_label="melody")
        written_file = tmp_path / "_tmp_melody.abc"
        assert written_file.exists()
        assert written_file.read_text(encoding="utf-8") == abc_text

    @patch("clef_server.tools.validate_abc")
    def test_sanitizes_voice_label_in_filename(self, mock_validate, tmp_path):
        mock_validate.return_value = {"ok": True}
        report_path = tmp_path / "report.json"
        run_validation_from_abc("X:1\nK:C\nC", tmp_path / "plan.json", report_path, tmp_path, voice_label="V:1+V:2 test")
        written_file = tmp_path / "_tmp_V_1_V_2_test.abc"
        assert written_file.exists()

    @patch("clef_server.tools.validate_abc")
    def test_handles_corrupt_report(self, mock_validate, tmp_path):
        mock_validate.return_value = {"ok": True}
        report_path = tmp_path / "report.json"
        report_path.write_text("not json{{{", encoding="utf-8")
        result = run_validation_from_abc("X:1\nK:C\nC", tmp_path / "plan.json", report_path, tmp_path)
        assert result == []
