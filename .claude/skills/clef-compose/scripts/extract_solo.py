"""Solo track extraction from MIDI files.

Given a MIDI file and a time range in seconds, extracts each non-tempo
track into its own standalone MIDI file so the user can listen to individual
instruments in isolation.

Usage:
    from extract_solo import extract_solo
    files = extract_solo("song.mid", 0.5, 2.0, "output_dir")
"""

import os
from typing import Optional

import mido


# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_BPM = 120

# GM program name mapping for readable filenames
PROGRAM_NAMES = {
    0: 'Piano',
    24: 'Guitar',
    32: 'Bass',
    40: 'Violin',
    48: 'Strings',
    56: 'Trumpet',
    65: 'Alto_Sax',
    73: 'Flute',
    80: 'Synth_Lead',
}


# ── Helpers ────────────────────────────────────────────────────────────────


def _get_tempo_bpm(midi: mido.MidiFile) -> float:
    """Extract tempo from track 0. Returns BPM (default 120)."""
    tempo_us = 500000  # Default: 120 BPM
    for msg in midi.tracks[0]:
        if msg.type == 'set_tempo':
            tempo_us = msg.tempo
            break
    return 60000000.0 / tempo_us


def _sec_to_ticks(sec: float, ticks_per_beat: int, bpm: float) -> int:
    """Convert seconds to MIDI ticks."""
    return int(sec * ticks_per_beat * bpm / 60.0)


def _get_track_name(track: mido.MidiTrack, index: int) -> str:
    """Determine a human-readable name for a track.

    Priority:
    1. track.name (if set and non-empty)
    2. program_change event -> PROGRAM_NAMES lookup
    3. Fallback: "instrument_{program}" or "track_{index}"
    """
    # Check explicit track name
    if track.name:
        return track.name

    # Check for program_change event
    program: Optional[int] = None
    for msg in track:
        if msg.type == 'program_change':
            program = msg.program
            break

    if program is not None:
        return PROGRAM_NAMES.get(program, f'instrument_{program}')

    return f'track_{index}'


def _is_tempo_track(track: mido.MidiTrack) -> bool:
    """Check if a track is the tempo/meta track (contains set_tempo events)."""
    return any(msg.type == 'set_tempo' for msg in track)


def _filter_track_events(
    track: mido.MidiTrack,
    start_ticks: int,
    end_ticks: int,
) -> tuple[list[tuple[int, object]], list[mido.Message]]:
    """Filter events within [start_ticks, end_ticks).

    Includes note_off events for notes that started before start_ticks
    (boundary note_off inclusion). The range is half-open: note_on events
    at exactly end_ticks are excluded, but note_off events at end_ticks
    are included to properly close notes.

    Returns:
        A tuple of (in_range_events, pre_range_setup) where:
        - in_range_events: list of (absolute_time, message) for events in range
        - pre_range_setup: list of program_change messages before the range
          (needed so the extracted MIDI uses the correct instrument)
    """
    events: list[tuple[int, object]] = []
    pre_range_setup: list[mido.Message] = []
    abs_time = 0
    # Track notes active before start_ticks for boundary note_off inclusion
    pre_range_active: set[int] = set()
    seen_program_change = False

    for msg in track:
        abs_time += msg.time

        if msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            # Boundary note_off: note started before range, ends inside range
            if msg.note in pre_range_active and start_ticks <= abs_time <= end_ticks:
                events.append((abs_time, msg))
            pre_range_active.discard(msg.note)
            continue

        if msg.type == 'note_on' and msg.velocity > 0:
            if abs_time < start_ticks:
                # Note started before range — track for boundary note_off
                pre_range_active.add(msg.note)
                continue
            if start_ticks <= abs_time < end_ticks:
                events.append((abs_time, msg))
            continue

        # program_change before range: save for setup
        if msg.type == 'program_change' and abs_time <= start_ticks:
            if not seen_program_change:
                pre_range_setup.append(msg)
                seen_program_change = True
            continue

        # Other events (control_change, etc.)
        if start_ticks <= abs_time < end_ticks:
            events.append((abs_time, msg))

    return events, pre_range_setup


def _build_solo_midi(
    tempo_track: mido.MidiTrack,
    filtered_events: list[tuple[int, object]],
    pre_range_setup: list[mido.Message],
    ticks_per_beat: int,
    start_ticks: int,
) -> Optional[mido.MidiFile]:
    """Build a standalone MIDI file from tempo track + filtered events.

    Returns None if there are no events to include (pre_range_setup alone
    does not count).
    """
    if not filtered_events:
        return None

    midi = mido.MidiFile()
    midi.ticks_per_beat = ticks_per_beat

    # Clone tempo track
    new_tempo = mido.MidiTrack()
    for msg in tempo_track:
        new_tempo.append(msg.copy(time=0))
    midi.tracks.append(new_tempo)

    # Build voice track with adjusted delta times
    voice = mido.MidiTrack()

    # Prepend program_change at time 0 so the instrument is correct
    for msg in pre_range_setup:
        voice.append(msg.copy(time=0))

    prev_time = start_ticks

    for abs_time, msg in filtered_events:
        delta = abs_time - prev_time
        new_msg = msg.copy(time=max(0, delta))
        voice.append(new_msg)
        prev_time = abs_time

    midi.tracks.append(voice)
    return midi


def _sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filenames."""
    for ch in ('/', '\\', ':', '*', '?', '"', '<', '>', '|'):
        name = name.replace(ch, '_')
    return name.strip('. ')


# ── Public API ─────────────────────────────────────────────────────────────


def extract_solo(
    midi_path: str,
    start_sec: float,
    end_sec: float,
    output_dir: str,
) -> list[str]:
    """Extract individual tracks from a MIDI file for a given time range.

    Each non-tempo track is saved as a standalone MIDI file containing
    the tempo track plus the filtered voice track.

    Args:
        midi_path: Path to the source MIDI file.
        start_sec: Start time in seconds.
        end_sec: End time in seconds.
        output_dir: Directory to save extracted files.

    Returns:
        List of created file paths.
    """
    midi = mido.MidiFile(midi_path)
    bpm = _get_tempo_bpm(midi)
    ticks_per_beat = midi.ticks_per_beat

    start_ticks = _sec_to_ticks(start_sec, ticks_per_beat, bpm)
    end_ticks = _sec_to_ticks(end_sec, ticks_per_beat, bpm)

    # Find the tempo track (first track with set_tempo, or track 0)
    tempo_track = midi.tracks[0]

    os.makedirs(output_dir, exist_ok=True)
    created_files: list[str] = []

    for i, track in enumerate(midi.tracks):
        # Skip tempo/meta tracks
        if i == 0 or _is_tempo_track(track):
            continue

        filtered, pre_range_setup = _filter_track_events(track, start_ticks, end_ticks)
        solo_midi = _build_solo_midi(tempo_track, filtered, pre_range_setup, ticks_per_beat, start_ticks)

        if solo_midi is None:
            continue

        track_name = _sanitize_filename(_get_track_name(track, i))
        filename = f'{track_name}_{start_sec}-{end_sec}.mid'
        filepath = os.path.join(output_dir, filename)
        solo_midi.save(filepath)
        created_files.append(filepath)

    return created_files
