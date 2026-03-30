"""MIDI piano roll analysis module.

Reads a MIDI file and generates a compact text report suitable for
LLM agent consumption (Reviewer, Leader). Uses ``mido`` only.
"""

import statistics
from typing import Any

import mido


# ── GM Level 1 Instrument Names (complete, 0-127) ─────────────────────────

GM_PROGRAM_NAMES: dict[int, str] = {
    # Piano (0-7)
    0: "Acoustic Grand Piano",
    1: "Bright Acoustic Piano",
    2: "Electric Grand Piano",
    3: "Honky-tonk Piano",
    4: "Electric Piano 1",
    5: "Electric Piano 2",
    6: "Harpsichord",
    7: "Clavinet",
    # Chromatic Percussion (8-15)
    8: "Celesta",
    9: "Glockenspiel",
    10: "Music Box",
    11: "Vibraphone",
    12: "Marimba",
    13: "Xylophone",
    14: "Tubular Bells",
    15: "Dulcimer",
    # Organ (16-23)
    16: "Drawbar Organ",
    17: "Percussive Organ",
    18: "Rock Organ",
    19: "Church Organ",
    20: "Reed Organ",
    21: "Accordion",
    22: "Harmonica",
    23: "Tango Accordion",
    # Guitar (24-31)
    24: "Acoustic Guitar(nylon)",
    25: "Acoustic Guitar(steel)",
    26: "Electric Guitar(jazz)",
    27: "Electric Guitar(clean)",
    28: "Electric Guitar(muted)",
    29: "Overdriven Guitar",
    30: "Distortion Guitar",
    31: "Guitar Harmonics",
    # Bass (32-39)
    32: "Acoustic Bass",
    33: "Electric Bass(finger)",
    34: "Electric Bass(pick)",
    35: "Fretless Bass",
    36: "Slap Bass 1",
    37: "Slap Bass 2",
    38: "Synth Bass 1",
    39: "Synth Bass 2",
    # Strings (40-47)
    40: "Violin",
    41: "Viola",
    42: "Cello",
    43: "Contrabass",
    44: "Tremolo Strings",
    45: "Pizzicato Strings",
    46: "Orchestral Harp",
    47: "Timpani",
    # Ensemble (48-55)
    48: "String Ensemble 1",
    49: "String Ensemble 2",
    50: "SynthStrings 1",
    51: "SynthStrings 2",
    52: "Choir Aahs",
    53: "Voice Oohs",
    54: "Synth Choir",
    55: "Orchestra Hit",
    # Brass (56-63)
    56: "Trumpet",
    57: "Trombone",
    58: "Tuba",
    59: "Muted Trumpet",
    60: "French Horn",
    61: "Brass Section",
    62: "Synth Brass 1",
    63: "Synth Brass 2",
    # Reed (64-71)
    64: "Soprano Sax",
    65: "Alto Sax",
    66: "Tenor Sax",
    67: "Baritone Sax",
    68: "Oboe",
    69: "English Horn",
    70: "Bassoon",
    71: "Clarinet",
    # Pipe (72-79)
    72: "Piccolo",
    73: "Flute",
    74: "Recorder",
    75: "Pan Flute",
    76: "Blown Bottle",
    77: "Shakuhachi",
    78: "Whistle",
    79: "Ocarina",
    # Synth Lead (80-87)
    80: "Synth Lead 1(square)",
    81: "Synth Lead 2(saw)",
    82: "Synth Lead 3(calliope)",
    83: "Synth Lead 4(chiff)",
    84: "Synth Lead 5(charang)",
    85: "Synth Lead 6(voice)",
    86: "Synth Lead 7(fifths)",
    87: "Synth Lead 8(bass+lead)",
    # Synth Pad (88-95)
    88: "Synth Pad 1(new age)",
    89: "Synth Pad 2(warm)",
    90: "Synth Pad 3(polysynth)",
    91: "Synth Pad 4(choir)",
    92: "Synth Pad 5(bowed)",
    93: "Synth Pad 6(metallic)",
    94: "Synth Pad 7(halo)",
    95: "Synth Pad 8(sweep)",
    # FX (96-103)
    96: "FX 1(rain)",
    97: "FX 2(soundtrack)",
    98: "FX 3(crystal)",
    99: "FX 4(atmosphere)",
    100: "FX 5(brightness)",
    101: "FX 6(goblins)",
    102: "FX 7(echoes)",
    103: "FX 8(sci-fi)",
    # Ethnic (104-111)
    104: "Sitar",
    105: "Banjo",
    106: "Shamisen",
    107: "Koto",
    108: "Kalimba",
    109: "Bagpipe",
    110: "Fiddle",
    111: "Shanai",
    # Percussive (112-119)
    112: "Tinkle Bell",
    113: "Agogo",
    114: "Steel Drums",
    115: "Woodblock",
    116: "Taiko Drum",
    117: "Melodic Tom",
    118: "Synth Drum",
    119: "Reverse Cymbal",
    # Sound Effects (120-127)
    120: "Guitar Fret Noise",
    121: "Breath Noise",
    122: "Seashore",
    123: "Bird Tweet",
    124: "Telephone Ring",
    125: "Helicopter",
    126: "Applause",
    127: "Gunshot",
}

# Unicode density bars (8 levels)
_DENSITY_BARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_DENSITY_BAR_MAX_LEVEL = len(_DENSITY_BARS) - 1  # 7

# Channel 9 (drums) — skip pitch analysis
_DRUM_CHANNEL = 9


# ── Public API ───────────────────────────────────────────────────────────


def analyze(midi_path: str, segment_sec: float = 2.0) -> str:
    """Analyze MIDI file and return compact text report."""
    import os as _os

    if not _os.path.isfile(midi_path):
        return f"MIDI Analysis Error: file not found: {midi_path}"
    if segment_sec <= 0:
        raise ValueError(f"segment_sec must be positive, got {segment_sec}")

    try:
        midi = mido.MidiFile(midi_path)
    except (OSError, ValueError, IOError) as e:
        return f"MIDI Analysis Error: failed to read {midi_path}: {e}"

    channels = _parse_tracks(midi)

    total_notes = sum(len(ch["notes"]) for ch in channels)
    if total_notes == 0:
        return "MIDI Analysis: no notes found"

    tempo = _detect_tempo(midi)
    total_sec = _total_duration_sec(midi, tempo)
    ticks_per_beat = midi.ticks_per_beat

    lines: list[str] = []
    lines.append(_format_header(midi_path, total_sec, tempo))
    lines.append(_format_per_channel(channels))
    lines.append(_format_density(channels, total_sec, segment_sec, ticks_per_beat, tempo))
    lines.append(_format_overlap(channels))
    lines.append(_format_velocity(channels))
    lines.append(_format_gaps(channels, ticks_per_beat, tempo))

    return "\n\n".join(lines)


# ── Internal Helpers ─────────────────────────────────────────────────────


def _parse_tracks(midi: mido.MidiFile) -> list[dict[str, Any]]:
    """Extract per-channel note data.

    Returns list of dicts:
        {channel, program, notes: [(abs_tick, note, velocity, dur_ticks)]}
    Sorted by channel number.
    """
    # Accumulate program changes per channel (value before first note)
    channel_programs: dict[int, int] = {}
    # Track open note_on events: (channel, note) -> (abs_tick, velocity)
    open_notes: dict[tuple[int, int], tuple[int, int]] = {}
    # Collect finished notes per channel
    channel_notes: dict[int, list[tuple[int, int, int, int]]] = {}
    abs_tick = 0

    for track in midi.tracks:
        for msg in track:
            abs_tick += msg.time
            if msg.type == "program_change":
                channel_programs[msg.channel] = msg.program
            elif msg.type == "note_on" and msg.velocity > 0:
                open_notes[(msg.channel, msg.note)] = (abs_tick, msg.velocity)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                key = (msg.channel, msg.note)
                if key in open_notes:
                    start_tick, vel = open_notes.pop(key)
                    dur = abs_tick - start_tick
                    channel_notes.setdefault(msg.channel, []).append(
                        (start_tick, msg.note, vel, dur)
                    )

    # Handle notes without note_off: default duration = 1 beat (ticks_per_beat)
    default_dur = midi.ticks_per_beat
    for (ch, note), (start_tick, vel) in open_notes.items():
        channel_notes.setdefault(ch, []).append((start_tick, note, vel, default_dur))

    # Build result sorted by channel
    result: list[dict[str, Any]] = []
    for ch in sorted(channel_notes):
        result.append({
            "channel": ch,
            "program": channel_programs.get(ch, 0),
            "notes": sorted(channel_notes[ch]),
        })

    return result


def _detect_tempo(midi: mido.MidiFile) -> float:
    """Return first tempo event in BPM, default 120."""
    for track in midi.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                return mido.tempo2bpm(msg.tempo)
    return 120.0


def _total_duration_sec(midi: mido.MidiFile, tempo: float) -> float:
    """Convert max absolute tick to seconds.

    Assumes Type 1 MIDI (tracks play simultaneously).
    For Type 0 (single-track), this still works since all events are in one track.
    """
    abs_tick = 0
    max_tick = 0
    for track in midi.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if abs_tick > max_tick:
                max_tick = abs_tick
    sec_per_tick = 60.0 / (tempo * midi.ticks_per_beat)
    return max_tick * sec_per_tick


def _midi_note_name(note: int) -> str:
    """MIDI number to note name: 60 -> 'C4'."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (note // 12) - 1
    return f"{names[note % 12]}{octave}"


def _program_name(program: int) -> str:
    """Program number to GM name, fallback to 'Prog.N'."""
    return GM_PROGRAM_NAMES.get(program, f"Prog.{program}")


def _ticks_to_sec(tick: int, ticks_per_beat: int, tempo: float) -> float:
    return tick * 60.0 / (tempo * ticks_per_beat)


# ── Format Sections ──────────────────────────────────────────────────────


def _format_header(path: str, total_sec: float, tempo: float) -> str:
    """e.g. 'MIDI Analysis: song.mid (28.0s, 120 BPM)'"""
    from os.path import basename
    name = basename(path)
    return f"MIDI Analysis: {name} ({total_sec:.1f}s, {int(tempo)} BPM)"


def _format_per_channel(channels: list[dict[str, Any]]) -> str:
    """Table with note count, pitch range, velocity stats."""
    lines = ["── Per-Channel ──────────────────────"]
    for ch in channels:
        notes = ch["notes"]
        ch_num = ch["channel"]
        is_drum = ch_num == _DRUM_CHANNEL
        prog_name = _program_name(ch["program"])
        label = f"Ch{ch_num} {prog_name}"

        note_count = len(notes)
        velocities = [n[2] for n in notes]

        if is_drum:
            pitch_range = "--"
            semitones = "--"
        else:
            pitches = [n[1] for n in notes]
            lo, hi = min(pitches), max(pitches)
            pitch_range = f"{_midi_note_name(lo)}-{_midi_note_name(hi)}"
            semitones = f"{hi - lo}st"

        vel_min = min(velocities)
        vel_max = max(velocities)
        vel_avg = statistics.fmean(velocities)

        lines.append(
            f"{label:<20s} notes:{note_count:<4d} {pitch_range:<8s} "
            f"vel:{vel_min}-{vel_max}  avg:{vel_avg:.0f}  range:{semitones}"
        )
    return "\n".join(lines)


def _format_density(
    channels: list[dict[str, Any]],
    total_sec: float,
    segment_sec: float,
    ticks_per_beat: int,
    tempo: float,
) -> str:
    """Unicode density bars per segment."""
    num_segments = max(1, int(total_sec / segment_sec))
    seg_ticks = int(segment_sec * 60.0 * ticks_per_beat / tempo)
    lines = [f"── Density (per {int(segment_sec)}s) ──────────────"]

    for ch in channels:
        ch_num = ch["channel"]
        prog_name = _program_name(ch["program"])
        label = f"Ch{ch_num} {prog_name}"

        # Count notes per segment
        counts = [0] * num_segments
        for start_tick, _, _, dur_ticks in ch["notes"]:
            end_tick = start_tick + dur_ticks
            seg_start = 0
            for i in range(num_segments):
                seg_end = seg_start + seg_ticks
                # Note overlaps segment if start < seg_end and end > seg_start
                if start_tick < seg_end and end_tick > seg_start:
                    counts[i] += 1
                seg_start = seg_end

        max_count = max(counts) if counts else 1
        if max_count == 0:
            max_count = 1
        bar = ""
        for c in counts:
            level = int(c / max_count * _DENSITY_BAR_MAX_LEVEL)
            if c > 0 and level == 0:
                level = 1
            bar += _DENSITY_BARS[level]

        lines.append(f"{label:<20s} {bar}")

    return "\n".join(lines)


def _format_overlap(channels: list[dict[str, Any]]) -> str:
    """Pairwise pitch range overlap detection."""
    # Filter non-drum channels with notes
    melodic = [ch for ch in channels if ch["channel"] != _DRUM_CHANNEL]

    if len(melodic) < 2:
        return "── Register Overlap ───────────────\n  N/A (single melodic channel)"

    lines = ["── Register Overlap ───────────────"]
    for i in range(len(melodic)):
        for j in range(i + 1, len(melodic)):
            ch_a = melodic[i]
            ch_b = melodic[j]
            pitches_a = {n[1] for n in ch_a["notes"]}
            pitches_b = {n[1] for n in ch_b["notes"]}
            overlap_semitones = len(pitches_a & pitches_b)

            if overlap_semitones > 12:
                level = "WARN (!)"
            elif overlap_semitones >= 7:
                level = "INFO"
            else:
                level = ""

            lines.append(
                f"Ch{ch_a['channel']} <-> Ch{ch_b['channel']}  "
                f"{overlap_semitones}st  {level}"
            )

    return "\n".join(lines)


def _format_velocity(channels: list[dict[str, Any]]) -> str:
    """Velocity flatness analysis."""
    lines = ["── Velocity Distribution ──────────"]
    for ch in channels:
        velocities = [n[2] for n in ch["notes"]]
        if len(velocities) < 2:
            lines.append(f"Ch{ch['channel']}  (insufficient data)")
            continue

        vel_std = statistics.stdev(velocities)
        vel_range = max(velocities) - min(velocities)
        vel_mean = statistics.mean(velocities)

        # Flatness ratio: std / mean
        flatness = vel_std / vel_mean if vel_mean > 0 else 0

        if flatness < 0.1:
            label = "flat (!)"
        elif flatness < 0.3:
            label = "moderate"
        else:
            label = "varied"

        lines.append(f"Ch{ch['channel']}  flatness:{flatness:.2f}  {label}")

    return "\n".join(lines)


def _format_gaps(
    channels: list[dict[str, Any]],
    ticks_per_beat: int,
    tempo: float,
) -> str:
    """Detect rhythm gaps > 2x median."""
    lines = ["── Rhythm Gaps ────────────────────"]
    has_gaps = False

    for ch in channels:
        notes = ch["notes"]
        if len(notes) < 2:
            continue

        # Compute gaps between consecutive note ends and next note starts
        # Notes are pre-sorted by _parse_tracks, but re-sort defensively
        sorted_notes = notes  # already sorted by start_tick
        gaps: list[float] = []
        for k in range(len(sorted_notes) - 1):
            end_tick = sorted_notes[k][0] + sorted_notes[k][3]
            next_start = sorted_notes[k + 1][0]
            gap_ticks = next_start - end_tick
            if gap_ticks > 0:
                gaps.append(gap_ticks)

        if not gaps:
            continue

        median_ticks = statistics.median(gaps)
        if median_ticks <= 0:
            median_ticks = 1

        threshold_ticks = median_ticks * 2.0
        for k, gap_ticks in enumerate(gaps):
            if gap_ticks <= threshold_ticks:
                continue
            has_gaps = True
            gap_sec = _ticks_to_sec(gap_ticks, ticks_per_beat, tempo)
            # Find approximate start time of gap
            end_tick = sorted_notes[k][0] + sorted_notes[k][3]
            start_sec = _ticks_to_sec(end_tick, ticks_per_beat, tempo)
            end_sec = _ticks_to_sec(
                sorted_notes[k + 1][0], ticks_per_beat, tempo
            )
            ratio = gap_ticks / median_ticks
            lines.append(
                f"Ch{ch['channel']}  {start_sec:.1f}s-{end_sec:.1f}s "
                f"gap {gap_sec:.1f}s ({ratio:.1f}x median)"
            )

    if not has_gaps:
        lines.append("  No significant gaps detected")

    return "\n".join(lines)
