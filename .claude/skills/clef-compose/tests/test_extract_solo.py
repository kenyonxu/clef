"""Tests for solo track extraction (Task 8)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import mido
import tempfile
from extract_solo import extract_solo


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_test_midi():
    """Create a multi-track MIDI file: tempo + melody + bass."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    # Tempo track
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(tempo_track)

    # Melody track (120 BPM -> 480 ticks/sec)
    melody = mido.MidiTrack()
    melody.name = "Flute"
    melody.append(mido.Message('program_change', program=73, channel=0, time=0))
    # Note at t=0, duration 1 beat (480 ticks)
    melody.append(mido.Message('note_on', note=60, velocity=100, channel=0, time=0))
    melody.append(mido.Message('note_off', note=60, velocity=100, channel=0, time=480))
    # Note at t=480, duration 1 beat
    melody.append(mido.Message('note_on', note=64, velocity=100, channel=0, time=0))
    melody.append(mido.Message('note_off', note=64, velocity=100, channel=0, time=480))
    mid.tracks.append(melody)

    # Bass track
    bass = mido.MidiTrack()
    bass.name = "Bass"
    bass.append(mido.Message('program_change', program=32, channel=1, time=0))
    # Note at t=0, duration 2 beats (960 ticks)
    bass.append(mido.Message('note_on', note=36, velocity=100, channel=1, time=0))
    bass.append(mido.Message('note_off', note=36, velocity=100, channel=1, time=960))
    mid.tracks.append(bass)

    return mid


# ── Task 8: Basic Extraction ──────────────────────────────────────────────

def test_extract_solo_by_track():
    """Each non-tempo track should produce one solo MIDI file."""
    mid = _make_test_midi()

    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        midi_path = f.name
    mid.save(midi_path)

    try:
        with tempfile.TemporaryDirectory() as output_dir:
            files = extract_solo(midi_path, 0.0, 2.0, output_dir)
            assert len(files) == 2, f"Expected 2 files, got {len(files)}"

            # Each file must have tempo + one voice track
            for f in files:
                solo = mido.MidiFile(f)
                assert len(solo.tracks) == 2, f"Expected 2 tracks in {f}, got {len(solo.tracks)}"
    finally:
        os.unlink(midi_path)


def test_extract_solo_tempo_preserved():
    """Each solo file must contain the tempo meta event."""
    mid = _make_test_midi()

    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        midi_path = f.name
    mid.save(midi_path)

    try:
        with tempfile.TemporaryDirectory() as output_dir:
            files = extract_solo(midi_path, 0.0, 2.0, output_dir)
            for f in files:
                solo = mido.MidiFile(f)
                tempo_track = solo.tracks[0]
                has_tempo = any(
                    msg.type == 'set_tempo' for msg in tempo_track
                )
                assert has_tempo, f"No tempo event in {f}"
    finally:
        os.unlink(midi_path)


def test_extract_solo_single_track():
    """Only events from the correct track should be present."""
    mid = _make_test_midi()

    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        midi_path = f.name
    mid.save(midi_path)

    try:
        with tempfile.TemporaryDirectory() as output_dir:
            files = extract_solo(midi_path, 0.0, 2.0, output_dir)
            for f in files:
                solo = mido.MidiFile(f)
                voice_track = solo.tracks[1]
                # All channel messages should be on the same channel
                channels = set()
                for msg in voice_track:
                    if msg.type == 'channel':
                        channels.add(msg.channel)
                assert len(channels) <= 1, f"Multiple channels in {f}: {channels}"
    finally:
        os.unlink(midi_path)


# ── Time Range Filtering ──────────────────────────────────────────────────

def test_extract_time_range():
    """Events outside the time range should be excluded."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    # Tempo track (120 BPM → 960 ticks/sec)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(tempo_track)

    # Melody track with notes at abs ticks: 0, 480, 960, 1440
    # (seconds: 0.0, 0.5, 1.0, 1.5)
    melody = mido.MidiTrack()
    melody.name = "Piano"
    melody.append(mido.Message('program_change', program=0, channel=0, time=0))
    for i in range(4):
        melody.append(mido.Message('note_on', note=60 + i, velocity=100, channel=0, time=0))
        melody.append(mido.Message('note_off', note=60 + i, velocity=100, channel=0, time=480))
    mid.tracks.append(melody)

    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        midi_path = f.name
    mid.save(midi_path)

    try:
        with tempfile.TemporaryDirectory() as output_dir:
            # Extract 0.5-1.0 seconds (480-960 ticks) — should capture 2nd note only
            files = extract_solo(midi_path, 0.5, 1.0, output_dir)
            assert len(files) == 1

            solo = mido.MidiFile(files[0])
            voice = solo.tracks[1]
            note_ons = [msg for msg in voice if msg.type == 'note_on']
            assert len(note_ons) == 1, f"Expected 1 note_on, got {len(note_ons)}"
            assert note_ons[0].note == 61, f"Expected note 61, got {note_ons[0].note}"
    finally:
        os.unlink(midi_path)


def test_extract_empty_range():
    """Graceful handling when no events fall in range."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(tempo_track)

    melody = mido.MidiTrack()
    melody.name = "Piano"
    melody.append(mido.Message('program_change', program=0, channel=0, time=0))
    # One note at t=0, duration 480 ticks (0-1 sec)
    melody.append(mido.Message('note_on', note=60, velocity=100, channel=0, time=0))
    melody.append(mido.Message('note_off', note=60, velocity=100, channel=0, time=480))
    mid.tracks.append(melody)

    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        midi_path = f.name
    mid.save(midi_path)

    try:
        with tempfile.TemporaryDirectory() as output_dir:
            # Extract 5.0-10.0 seconds — no events here
            files = extract_solo(midi_path, 5.0, 10.0, output_dir)
            assert len(files) == 0, f"Expected 0 files for empty range, got {len(files)}"
    finally:
        os.unlink(midi_path)


def test_extract_boundary_note_off():
    """If a note started before start_ticks, include its note_off."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(tempo_track)

    melody = mido.MidiTrack()
    melody.name = "Guitar"
    melody.append(mido.Message('program_change', program=24, channel=0, time=0))
    # Long note from t=0 to t=960 (0-2 sec)
    melody.append(mido.Message('note_on', note=60, velocity=100, channel=0, time=0))
    melody.append(mido.Message('note_off', note=60, velocity=100, channel=0, time=960))
    mid.tracks.append(melody)

    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        midi_path = f.name
    mid.save(midi_path)

    try:
        with tempfile.TemporaryDirectory() as output_dir:
            # Extract 0.5-2.0 seconds (240-960 ticks)
            # note_on at t=0 is before range, but note_off at t=960 is inside
            files = extract_solo(midi_path, 0.5, 2.0, output_dir)
            assert len(files) == 1

            solo = mido.MidiFile(files[0])
            voice = solo.tracks[1]
            note_offs = [msg for msg in voice if msg.type == 'note_off']
            assert len(note_offs) == 1, f"Expected 1 note_off, got {len(note_offs)}"
    finally:
        os.unlink(midi_path)


# ── Track Naming ──────────────────────────────────────────────────────────

def test_extract_naming_from_track_name():
    """Filename should use the track name when available."""
    mid = _make_test_midi()

    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        midi_path = f.name
    mid.save(midi_path)

    try:
        with tempfile.TemporaryDirectory() as output_dir:
            files = extract_solo(midi_path, 0.0, 2.0, output_dir)
            basenames = [os.path.basename(f) for f in files]
            has_flute = any('Flute' in b for b in basenames)
            has_bass = any('Bass' in b for b in basenames)
            assert has_flute, f"No 'Flute' in filenames: {basenames}"
            assert has_bass, f"No 'Bass' in filenames: {basenames}"
    finally:
        os.unlink(midi_path)


def test_extract_naming_from_program():
    """Filename should use program name when track has no name."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(tempo_track)

    track = mido.MidiTrack()
    # No name set
    track.append(mido.Message('program_change', program=24, channel=0, time=0))
    track.append(mido.Message('note_on', note=60, velocity=100, channel=0, time=0))
    track.append(mido.Message('note_off', note=60, velocity=100, channel=0, time=480))
    mid.tracks.append(track)

    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        midi_path = f.name
    mid.save(midi_path)

    try:
        with tempfile.TemporaryDirectory() as output_dir:
            files = extract_solo(midi_path, 0.0, 2.0, output_dir)
            assert len(files) == 1
            basenames = [os.path.basename(f) for f in files]
            has_guitar = any('Guitar' in b for b in basenames)
            assert has_guitar, f"Expected 'Guitar' in filenames: {basenames}"
    finally:
        os.unlink(midi_path)


# ── Delta Time Adjustment ─────────────────────────────────────────────────

def test_extract_first_event_at_zero():
    """The first event in the extracted track should have time=0."""
    mid = mido.MidiFile()
    mid.ticks_per_beat = 480

    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    mid.tracks.append(tempo_track)

    melody = mido.MidiTrack()
    melody.name = "Piano"
    melody.append(mido.Message('program_change', program=0, channel=0, time=0))
    # Note at t=960 (2 sec), extracting from 1.5 sec (720 ticks)
    melody.append(mido.Message('note_on', note=60, velocity=100, channel=0, time=960))
    melody.append(mido.Message('note_off', note=60, velocity=100, channel=0, time=480))
    mid.tracks.append(melody)

    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        midi_path = f.name
    mid.save(midi_path)

    try:
        with tempfile.TemporaryDirectory() as output_dir:
            files = extract_solo(midi_path, 1.5, 3.0, output_dir)
            assert len(files) == 1

            solo = mido.MidiFile(files[0])
            voice = solo.tracks[1]
            # First message (program_change or note_on) should have time=0
            first_msg = voice[0]
            assert first_msg.time == 0, f"First event time should be 0, got {first_msg.time}"
    finally:
        os.unlink(midi_path)
