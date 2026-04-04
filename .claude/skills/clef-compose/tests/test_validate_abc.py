"""Tests for validate_abc.py — music21-based ABC score validation."""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from validate_abc import validate, ValidationReport, ValidationIssue

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def _write_abc(content: str) -> str:
    """Write ABC content to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix='.abc')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def _write_plan(data: dict) -> str:
    """Write plan JSON to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return path


# ---------------------------------------------------------------------------
# Clean ABC (all checks should pass)
# ---------------------------------------------------------------------------

class TestValidateCleanAbc:
    def test_no_fails_on_clean_abc(self):
        abc_path = os.path.join(FIXTURES, 'sample.abc')
        plan_path = os.path.join(FIXTURES, 'test_plan.json')
        report = validate(abc_path, plan_path)
        assert isinstance(report, ValidationReport)
        assert len(report.fails) == 0, f"Unexpected fails: {report.fails}"

    def test_passes_includes_all_categories(self):
        abc_path = os.path.join(FIXTURES, 'sample.abc')
        plan_path = os.path.join(FIXTURES, 'test_plan.json')
        report = validate(abc_path, plan_path)
        expected_categories = {
            'key_consistency', 'pitch_range', 'large_interval',
            'measure_duration', 'voice_alignment',
        }
        for cat in expected_categories:
            assert cat in report.passes, f"Missing pass: {cat}"


# ---------------------------------------------------------------------------
# Key consistency
# ---------------------------------------------------------------------------

class TestKeyConsistency:
    def test_wrong_key_produces_warning(self):
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/8\n"
            "Q:1/4=120\nK:G\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| d2 f2 a2 f2 | g2 b2 d'2 b2 |\n"
        )
        plan = {
            "title": "Test", "key": "D", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            key_warns = [w for w in report.warns if w.category == 'key_consistency']
            assert len(key_warns) > 0, "Expected key_consistency warning"
            assert key_warns[0].severity == 'warn'
            assert 'global' in key_warns[0].voice
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)

    def test_matching_key_no_warning(self):
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/8\n"
            "Q:1/4=120\nK:D\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| d2 f2 a2 f2 | g2 b2 d'2 b2 |\n"
        )
        plan = {
            "title": "Test", "key": "D", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            key_warns = [w for w in report.warns if w.category == 'key_consistency']
            assert len(key_warns) == 0
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)


# ---------------------------------------------------------------------------
# Pitch range
# ---------------------------------------------------------------------------

class TestPitchRange:
    def test_notes_out_of_range_produces_fail(self):
        # Use very low notes (,,) to go below C2 range
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/8\n"
            "Q:1/4=120\nK:C\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| C,,2 C,,2 C,,2 C,,2 | D2 E2 F2 G2 |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            pitch_fails = [f for f in report.fails if f.category == 'pitch_range']
            assert len(pitch_fails) > 0, "Expected pitch_range fail for notes below Flute range"
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)

    def test_notes_within_range_no_fail(self):
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/8\n"
            "Q:1/4=120\nK:C\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| c2 d2 e2 f2 | g2 a2 b2 c'2 |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            pitch_fails = [f for f in report.fails if f.category == 'pitch_range']
            assert len(pitch_fails) == 0, f"Unexpected pitch_range fails: {pitch_fails}"
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)


# ---------------------------------------------------------------------------
# Large interval detection
# ---------------------------------------------------------------------------

class TestLargeInterval:
    def test_large_interval_produces_warning(self):
        # Jump from C to high c' (> 5 semitones)
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/8\n"
            "Q:1/4=120\nK:C\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| c2 c''2 c2 c2 |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            interval_warns = [w for w in report.warns if w.category == 'large_interval']
            assert len(interval_warns) > 0, "Expected large_interval warning"
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)

    def test_small_intervals_no_warning(self):
        # All steps within 5 semitones
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/8\n"
            "Q:1/4=120\nK:C\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| c2 d2 e2 f2 | g2 a2 g2 f2 |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            interval_warns = [w for w in report.warns if w.category == 'large_interval']
            assert len(interval_warns) == 0, f"Unexpected large_interval warnings: {interval_warns}"
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)


# ---------------------------------------------------------------------------
# Measure duration
# ---------------------------------------------------------------------------

class TestMeasureDuration:
    def test_incomplete_measure_produces_fail(self):
        # Only 3 quarter notes in 4/4 time = 3 QL, expected 4
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/4\n"
            "Q:1/4=120\nK:C\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| C D E |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            dur_fails = [f for f in report.fails if f.category == 'measure_duration']
            assert len(dur_fails) > 0, "Expected measure_duration fail"
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)

    def test_correct_measure_duration_no_fail(self):
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/4\n"
            "Q:1/4=120\nK:C\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| C D E F |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            dur_fails = [f for f in report.fails if f.category == 'measure_duration']
            assert len(dur_fails) == 0, f"Unexpected measure_duration fails: {dur_fails}"
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)


# ---------------------------------------------------------------------------
# Voice measure alignment
# ---------------------------------------------------------------------------

class TestVoiceAlignment:
    def test_misaligned_voices_produces_fail(self):
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/4\n"
            "Q:1/4=120\nK:C\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| C D E F | G A B c |\n"
            "V:2 name=\"Bass\" clef=bass\n"
            "| C, D, E, |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {
                "melody": {"channel": 0, "instrument": 73, "name": "Flute"},
                "bass": {"channel": 1, "instrument": 48, "name": "Bass"},
            },
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            align_fails = [f for f in report.fails if f.category == 'voice_alignment']
            assert len(align_fails) > 0, "Expected voice_alignment fail"
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)

    def test_aligned_voices_no_fail(self):
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/4\n"
            "Q:1/4=120\nK:C\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| C D E F |\n"
            "V:2 name=\"Bass\" clef=bass\n"
            "| C, D, E, F, |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {
                "melody": {"channel": 0, "instrument": 73, "name": "Flute"},
                "bass": {"channel": 1, "instrument": 48, "name": "Bass"},
            },
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            align_fails = [f for f in report.fails if f.category == 'voice_alignment']
            assert len(align_fails) == 0, f"Unexpected voice_alignment fails: {align_fails}"
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)


# ---------------------------------------------------------------------------
# ValidationReport dataclass
# ---------------------------------------------------------------------------

class TestValidationReport:
    def test_to_json(self):
        report = ValidationReport(
            fails=[ValidationIssue('test_cat', 'fail', 'V:1', 'test fail message')],
            warns=[ValidationIssue('test_cat2', 'warn', 'global', 'test warn message')],
            passes=['some_check'],
        )
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        try:
            report.to_json(path)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            assert len(data['fails']) == 1
            assert data['fails'][0]['severity'] == 'fail'
            assert len(data['warns']) == 1
            assert data['warns'][0]['severity'] == 'warn'
            assert len(data['passes']) == 1
        finally:
            os.unlink(path)

    def test_is_valid_property(self):
        clean = ValidationReport(fails=[], warns=[], passes=['a'])
        assert clean.is_valid is True

        dirty = ValidationReport(
            fails=[ValidationIssue('x', 'fail', 'V:1', 'bad')],
            warns=[],
            passes=['a'],
        )
        assert dirty.is_valid is False


# ---------------------------------------------------------------------------
# Chord duration calculation (Fix: [FAc]4 counts as one unit, not summed)
# ---------------------------------------------------------------------------

class TestChordDuration:
    def test_chord_with_duration_counts_as_single_unit(self):
        """[FAc]2 should be duration 1.0 beat (2 * 0.5), not 1.5 (old bug)."""
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/8\n"
            "Q:1/4=120\nK:C\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| [FAc]2 [FAc]2 [FAc]2 [FAc]2 |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            dur_fails = [f for f in report.fails if f.category == 'measure_duration']
            assert len(dur_fails) == 0, (
                f"Chord [FAc]2 x4 should sum to 4 beats but got fails: {dur_fails}"
            )
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)

    def test_chord_without_default_duration(self):
        """[FAc] without duration number should use default length (0.5 beats)."""
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/8\n"
            "Q:1/4=120\nK:C\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| [FAc] [FAc] [FAc] [FAc] [FAc] [FAc] [FAc] [FAc] |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            dur_fails = [f for f in report.fails if f.category == 'measure_duration']
            assert len(dur_fails) == 0, (
                f"8 chords [FAc] should sum to 4 beats but got fails: {dur_fails}"
            )
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)


# ---------------------------------------------------------------------------
# Exit code: warns-only should exit 0 (Fix: was exiting 2)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Orchestration layers (V:5+ voice_id mapping)
# ---------------------------------------------------------------------------

class TestOrchestrationLayers:
    def test_plan_with_layers_maps_voices_beyond_4(self):
        """Plan with orchestration.layers using voice_id should map V:5+ to layer instruments."""
        abc = (
            "X:1\nT:Test\nM:4/4\nL:1/8\nK:C\n"
            'V:1 name="Flute"\nc2 d2 e2 f2 |\n'
            'V:2 name="Strings"\nC2 E2 G2 C2 |\n'
            'V:3 name="Bass" clef=bass\nC,2 C,2 C,2 C,2 |\n'
            'V:4 name="Drums" clef=perc\nz4 z4 |\n'
            'V:5 name="Oboe"\nc2 d2 e2 f2 |\n'
        )
        plan = {
            "orchestration": {
                "melody": {"instrument": 73, "range": "C4-C7"},
                "harmony": {"instrument": 48, "range": "C3-C6"},
                "bass": {"instrument": 32, "range": "E2-E4"},
                "drums": {"instrument": 0},
                "layers": {
                    "counter_melody": {"instrument": 68, "range": "A4-G6", "voice_id": 5},
                }
            }
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            report = validate(abc_path, plan_path)
            fail_msgs = [i.message for i in report.fails]
            v5_range_fails = [m for m in fail_msgs if "V:5" in m and "range" in m.lower()]
            assert len(v5_range_fails) == 0, f"V:5 range fails: {v5_range_fails}"
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)


# ---------------------------------------------------------------------------
# Exit code: warns-only should exit 0 (Fix: was exiting 2)
# ---------------------------------------------------------------------------

class TestExitCode:
    def test_warns_only_exits_zero(self):
        """WARN-level issues should not cause non-zero exit code."""
        abc = (
            "%%abc-version 2.1\nX:1\nT:Test\nM:4/4\nL:1/8\n"
            "Q:1/4=120\nK:G\n"
            "V:1 name=\"Flute\" clef=treble\n"
            "| c2 d2 e2 f2 | g2 a2 g2 f2 |\n"
        )
        plan = {
            "title": "Test", "key": "C", "bpm": 120,  # Key mismatch → WARN
            "time_signature": "4/4",
            "orchestration": {"melody": {"channel": 0, "instrument": 73, "name": "Flute"}},
        }
        abc_path = _write_abc(abc)
        plan_path = _write_plan(plan)
        try:
            script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'validate_abc.py')
            result = subprocess.run(
                [sys.executable, script, abc_path, plan_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, (
                f"WARNs-only should exit 0 but got {result.returncode}. "
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        finally:
            os.unlink(abc_path)
            os.unlink(plan_path)
