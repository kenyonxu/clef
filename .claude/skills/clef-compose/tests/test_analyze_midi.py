"""Tests for MIDI piano roll analysis module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import mido
import tempfile
import pytest
from analyze_midi import (
    _midi_note_name,
    _detect_tempo,
    analyze,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_test_midi(tmp_path=None):
    """Create a multi-channel MIDI file for integration tests.

    Returns (mido.MidiFile, midi_path).
    If tmp_path is provided (pytest fixture), auto-cleanup is handled.
    Otherwise caller must os.unlink(midi_path).
    """
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    # Tempo track: 120 BPM (tempo=500000 microseconds per beat)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(tempo_track)

    # Channel 0 (Piano, program 0): 6 notes C4-E4-G4-C5-D5-E5
    # Notes 60-67, velocities 80-110
    piano = mido.MidiTrack()
    piano.append(mido.Message('program_change', program=0, channel=0, time=0))
    piano_notes = [
        (60, 80),   # C4
        (62, 90),   # D4
        (64, 100),  # E4
        (67, 105),  # G4
        (72, 110),  # C5
        (74, 95),   # D5
    ]
    for note, vel in piano_notes:
        piano.append(mido.Message('note_on', note=note, velocity=vel, channel=0, time=0))
        piano.append(mido.Message('note_off', note=note, velocity=0, channel=0, time=480))
    mid.tracks.append(piano)

    # Channel 1 (Strings, program 48): 3 notes C4-E4-G4 (overlapping with ch0)
    strings = mido.MidiTrack()
    strings.append(mido.Message('program_change', program=48, channel=1, time=0))
    string_notes = [
        (60, 85),   # C4
        (64, 90),   # E4
        (67, 88),   # G4
    ]
    # Add a deliberate 2-beat gap (960 ticks) between first group and remaining notes
    # First note at t=0
    strings.append(mido.Message('note_on', note=string_notes[0][0], velocity=string_notes[0][1], channel=1, time=0))
    strings.append(mido.Message('note_off', note=string_notes[0][0], velocity=0, channel=1, time=480))
    # Gap of 960 ticks (2 beats at 120 BPM = 1 second)
    strings.append(mido.Message('note_on', note=string_notes[1][0], velocity=string_notes[1][1], channel=1, time=960))
    strings.append(mido.Message('note_off', note=string_notes[1][0], velocity=0, channel=1, time=480))
    strings.append(mido.Message('note_on', note=string_notes[2][0], velocity=string_notes[2][1], channel=1, time=0))
    strings.append(mido.Message('note_off', note=string_notes[2][0], velocity=0, channel=1, time=480))
    mid.tracks.append(strings)

    # Write to temp file
    if tmp_path is not None:
        midi_path = str(tmp_path / "test.mid")
    else:
        tmp = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
        midi_path = tmp.name
        tmp.close()
    mid.save(midi_path)

    return mid, midi_path


def _make_empty_midi(tmp_path=None):
    """Create a MIDI file with no notes."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(tempo_track)

    if tmp_path is not None:
        midi_path = str(tmp_path / "empty.mid")
    else:
        tmp = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
        midi_path = tmp.name
        tmp.close()
    mid.save(midi_path)

    return midi_path


def _make_single_channel_midi(tmp_path=None):
    """Create a MIDI file with only one melodic channel."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(tempo_track)

    piano = mido.MidiTrack()
    piano.append(mido.Message('program_change', program=0, channel=0, time=0))
    piano.append(mido.Message('note_on', note=60, velocity=100, channel=0, time=0))
    piano.append(mido.Message('note_off', note=60, velocity=0, channel=0, time=480))
    piano.append(mido.Message('note_on', note=64, velocity=90, channel=0, time=0))
    piano.append(mido.Message('note_off', note=64, velocity=0, channel=0, time=480))
    mid.tracks.append(piano)

    if tmp_path is not None:
        midi_path = str(tmp_path / "single.mid")
    else:
        tmp = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
        midi_path = tmp.name
        tmp.close()
    mid.save(midi_path)

    return midi_path


def _make_no_overlap_midi(tmp_path=None):
    """Create a MIDI file with two non-overlapping pitch ranges."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(tempo_track)

    # Ch0: high notes C5-E5 (72-76)
    high = mido.MidiTrack()
    high.append(mido.Message('program_change', program=0, channel=0, time=0))
    high.append(mido.Message('note_on', note=72, velocity=100, channel=0, time=0))
    high.append(mido.Message('note_off', note=72, velocity=0, channel=0, time=480))
    high.append(mido.Message('note_on', note=76, velocity=100, channel=0, time=0))
    high.append(mido.Message('note_off', note=76, velocity=0, channel=0, time=480))
    mid.tracks.append(high)

    # Ch1: low notes C3-E3 (48-52)
    low = mido.MidiTrack()
    low.append(mido.Message('program_change', program=32, channel=1, time=0))
    low.append(mido.Message('note_on', note=48, velocity=100, channel=1, time=0))
    low.append(mido.Message('note_off', note=48, velocity=0, channel=1, time=480))
    low.append(mido.Message('note_on', note=52, velocity=100, channel=1, time=0))
    low.append(mido.Message('note_off', note=52, velocity=0, channel=1, time=480))
    mid.tracks.append(low)

    if tmp_path is not None:
        midi_path = str(tmp_path / "no_overlap.mid")
    else:
        tmp = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
        midi_path = tmp.name
        tmp.close()
    mid.save(midi_path)

    return midi_path


def _make_no_tempo_midi(tmp_path=None):
    """Create a MIDI file with no tempo event."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    piano = mido.MidiTrack()
    piano.append(mido.Message('program_change', program=0, channel=0, time=0))
    piano.append(mido.Message('note_on', note=60, velocity=100, channel=0, time=0))
    piano.append(mido.Message('note_off', note=60, velocity=0, channel=0, time=480))
    mid.tracks.append(piano)

    if tmp_path is not None:
        midi_path = str(tmp_path / "no_tempo.mid")
    else:
        tmp = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
        midi_path = tmp.name
        tmp.close()
    mid.save(midi_path)

    return midi_path


# ── Helper Tests: _midi_note_name ──────────────────────────────────────────

def test_midi_note_name_c4():
    assert _midi_note_name(60) == "C4"


def test_midi_note_name_a4():
    assert _midi_note_name(69) == "A4"


def test_midi_note_name_b4():
    assert _midi_note_name(71) == "B4"


# ── Helper Tests: _detect_tempo ────────────────────────────────────────────

def test_detect_tempo_from_event():
    """120 BPM = 500000 microseconds per beat."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480
    track = mido.MidiTrack()
    track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(track)

    bpm = _detect_tempo(mid)
    assert bpm == 120.0, f"Expected 120.0 BPM, got {bpm}"


def test_detect_tempo_default(tmp_path):
    """No tempo event → default 120 BPM."""
    midi_path = _make_no_tempo_midi(tmp_path)
    mid = mido.MidiFile(midi_path)
    bpm = _detect_tempo(mid)
    assert bpm == 120.0, f"Expected default 120.0, got {bpm}"


# ── Integration Tests: analyze() ───────────────────────────────────────────

def test_full_report_all_sections(tmp_path):
    """Multi-channel MIDI produces all 5 report sections."""
    _, midi_path = _make_test_midi(tmp_path)
    report = analyze(midi_path)
    assert "Per-Channel" in report
    assert "Density" in report
    assert "Register Overlap" in report
    assert "Velocity" in report
    assert "Rhythm Gaps" in report


def test_empty_midi_no_notes(tmp_path):
    """MIDI with no notes returns 'no notes found'."""
    midi_path = _make_empty_midi(tmp_path)
    report = analyze(midi_path)
    assert "no notes found" in report, f"Expected 'no notes found', got: {report}"


def test_single_channel_no_overlap(tmp_path):
    """Single melodic channel → overlap section shows N/A."""
    midi_path = _make_single_channel_midi(tmp_path)
    report = analyze(midi_path)
    assert "N/A" in report, f"Expected 'N/A' in overlap section, got: {report}"


def test_report_compactness(tmp_path):
    """Multi-track MIDI report should be under 5000 characters."""
    _, midi_path = _make_test_midi(tmp_path)
    report = analyze(midi_path)
    assert len(report) < 5000, f"Report too long: {len(report)} chars"


def test_overlapping_ranges_warning(tmp_path):
    """Two channels with overlapping pitch ranges → overlap line present."""
    _, midi_path = _make_test_midi(tmp_path)
    report = analyze(midi_path)
    # Ch0 has pitches {60,62,64,67,72,74}, Ch1 has {60,64,67}
    # Overlap = {60,64,67} = 3 unique pitches
    # With 3 overlapping semitones: < 7 → no label (empty string)
    # The overlap line should still be present
    assert "Ch0 <-> Ch1" in report, f"Expected overlap line, got: {report}"


def test_no_overlap_ok(tmp_path):
    """Non-overlapping pitch ranges → '0st' detected."""
    midi_path = _make_no_overlap_midi(tmp_path)
    report = analyze(midi_path)
    # Ch0 has pitches {72,76}, Ch1 has pitches {48,52}
    # Intersection is empty → 0st overlap
    assert "0st" in report, f"Expected '0st', got: {report}"


# ── Error Path Tests ───────────────────────────────────────────────────────

def test_nonexistent_file():
    """Non-existent file returns error message."""
    report = analyze("/nonexistent/path/song.mid")
    assert "MIDI Analysis Error" in report
    assert "not found" in report


def test_invalid_midi_file(tmp_path):
    """Non-MIDI file returns error message."""
    bad_path = str(tmp_path / "not_midi.txt")
    with open(bad_path, 'w') as f:
        f.write("this is not a midi file")
    report = analyze(bad_path)
    assert "MIDI Analysis Error" in report


def test_segment_sec_zero():
    """segment_sec=0 raises ValueError."""
    midi_path = _make_single_channel_midi()
    try:
        with pytest.raises(ValueError, match="segment_sec must be positive"):
            analyze(midi_path, segment_sec=0.0)
    finally:
        os.unlink(midi_path)


def test_segment_sec_negative():
    """segment_sec=-1 raises ValueError."""
    midi_path = _make_single_channel_midi()
    try:
        with pytest.raises(ValueError, match="segment_sec must be positive"):
            analyze(midi_path, segment_sec=-1.0)
    finally:
        os.unlink(midi_path)
