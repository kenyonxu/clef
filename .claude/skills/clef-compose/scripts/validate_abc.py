#!/usr/bin/env python3
"""music21-based ABC score validation.

Usage: python validate_abc.py <file.abc> <plan.json> [--json output.json]

Checks:
  1. Key consistency        (WARN)
  2. Pitch range            (FAIL)
  3. Large interval > 7st   (WARN)
  4. Measure duration       (FAIL)
  5. Voice measure alignment (FAIL)

Exit codes: 0=pass (warns are informational), 1=has fails
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

import music21


# ---------------------------------------------------------------------------
# Instrument pitch ranges (MIDI note numbers, inclusive)
# ---------------------------------------------------------------------------

INSTRUMENT_RANGES: dict[str, tuple[int, int]] = {
    "flute":        (60, 96),   # C4 - C7
    "violin":       (55, 105),  # G3 - A7
    "strings pad":  (48, 84),   # C3 - C6
    "strings":      (48, 84),   # alias
    "bass":         (40, 64),   # E2 - E4
    "synth lead":   (36, 96),   # C2 - C7
    "synth":        (36, 96),   # alias
}

DEFAULT_RANGE = (36, 96)  # C2 - C7

# SF2 profile (loaded via --sf2-profile, used to override INSTRUMENT_RANGES)
_sf2_profile: dict | None = None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    category: str   # 'key_consistency', 'pitch_range', etc.
    severity: str   # 'fail', 'warn', or 'info'
    voice: str      # 'V:1', 'V:2', or 'global'
    message: str    # Human-readable description


@dataclass
class ValidationReport:
    fails: list = field(default_factory=list)
    warns: list = field(default_factory=list)
    passes: list = field(default_factory=list)
    infos: list = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.fails) == 0

    def to_json(self, output_path: str) -> None:
        data = {
            "fails": [asdict(i) for i in self.fails],
            "warns": [asdict(i) for i in self.warns],
            "passes": list(self.passes),
            "infos": [asdict(i) for i in self.infos],
        }
        Path(output_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def __str__(self) -> str:
        lines = []
        for issue in self.fails:
            lines.append(f"  FAIL  [{issue.category}] {issue.voice}: {issue.message}")
        for issue in self.warns:
            lines.append(f"  WARN  [{issue.category}] {issue.voice}: {issue.message}")
        if self.passes:
            lines.append(f"  PASS  {', '.join(sorted(self.passes))}")
        for issue in self.infos:
            lines.append(f"  INFO  [{issue.category}] {issue.voice}: {issue.message}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _load_plan(plan_path: str) -> dict:
    with open(plan_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_abc(abc_path: str) -> music21.stream.Score:
    return music21.converter.parse(abc_path, format="abc")


def _get_instrument_range(voice_name: str, gm_instrument: int | None = None) -> tuple[int, int]:
    """Match voice name to an instrument range.

    Priority:
    1. SF2 profile lookup by GM instrument number (if profile loaded)
    2. Hardcoded INSTRUMENT_RANGES by name substring
    3. DEFAULT_RANGE
    """
    if _sf2_profile is not None and gm_instrument is not None:
        preset = _sf2_profile.get("presets", {}).get(str(gm_instrument))
        if preset and "key_range" in preset:
            return tuple(preset["key_range"])
    lower = voice_name.lower()
    for name, rng in INSTRUMENT_RANGES.items():
        if name in lower:
            return rng
    return DEFAULT_RANGE


def _voice_label(idx: int) -> str:
    """Convert 0-based part index to ABC voice label."""
    return f"V:{idx + 1}"


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _parse_abc_key(abc_path: str) -> str:
    """Extract the K: field directly from ABC text (reliable for short melodies)."""
    text = Path(abc_path).read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("K:"):
            return stripped[2:].strip()
    return ""


def check_key_consistency(score: music21.stream.Score, plan: dict, abc_path: str = "") -> ValidationIssue | None:
    """Compare ABC header key with plan key. Return warning on mismatch.

    Uses the K: field directly from ABC text rather than music21's
    analyze('key'), which is unreliable for short melodies.
    """
    plan_key = plan.get("key", "")
    if not plan_key or not abc_path:
        return None

    abc_key = _parse_abc_key(abc_path)
    if not abc_key:
        return None

    # Normalize both keys for comparison (case-insensitive)
    if plan_key.lower() != abc_key.lower():
        return ValidationIssue(
            category="key_consistency",
            severity="warn",
            voice="global",
            message=f"Plan key {plan_key} differs from ABC key {abc_key}",
        )
    return None


def _parse_voice_names(abc_path: str) -> dict[int, str]:
    """Extract voice names from ABC V: lines. Returns {voice_id: name}."""
    text = Path(abc_path).read_text(encoding="utf-8")
    voices: dict[int, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("V:"):
            rest = stripped[2:].strip()
            # Extract voice id (number before space or end of token)
            parts = rest.split(None, 1)
            voice_id_str = parts[0]
            try:
                voice_id = int(voice_id_str)
            except ValueError:
                continue
            # Extract name from name="..." attribute
            name = ""
            if len(parts) > 1:
                attrs = parts[1]
                if 'name="' in attrs:
                    start = attrs.index('name="') + 6
                    end = attrs.index('"', start)
                    name = attrs[start:end]
            if name:
                voices[voice_id] = name
    return voices


def check_pitch_range(score: music21.stream.Score, plan: dict, abc_path: str = "") -> list[ValidationIssue]:
    """Check all notes in each voice fall within instrument range."""
    issues: list[ValidationIssue] = []

    voice_names = _parse_voice_names(abc_path) if abc_path else {}

    # Build voice→GM instrument mapping from plan.json
    orchestration = plan.get("orchestration", {})
    voice_gm_map: dict[int, int | None] = {}
    for part_key, part_info in orchestration.items():
        voice_idx = {"melody": 1, "harmony": 2, "bass": 3, "drums": 4}.get(part_key)
        if voice_idx:
            voice_gm_map[voice_idx] = part_info.get("instrument")

    for idx, part in enumerate(score.parts):
        voice_label = _voice_label(idx)
        voice_id = idx + 1

        # Get instrument name: prefer ABC V: line, fallback to music21 metadata
        part_name = voice_names.get(voice_id, "")
        if not part_name:
            for el in part.recurse().getElementsByClass("Instrument"):
                part_name = el.instrumentName or ""
                break
        if not part_name:
            part_name = part.partName or ""

        gm_inst = voice_gm_map.get(voice_id)
        lo, hi = _get_instrument_range(part_name, gm_inst)

        for note in part.recurse().notes:
            # Handle both Note (.pitch) and Chord (.pitches) objects
            if hasattr(note, 'pitches'):
                midi_notes = [p.midi for p in note.pitches]
                pitch_names = [p.nameWithOctave for p in note.pitches]
            else:
                midi_notes = [note.pitch.midi]
                pitch_names = [note.pitch.nameWithOctave]

            for midi, pitch_name in zip(midi_notes, pitch_names):
                if midi < lo or midi > hi:
                    issues.append(ValidationIssue(
                        category="pitch_range",
                        severity="fail",
                        voice=voice_label,
                        message=(
                            f"Note {pitch_name} (MIDI {midi}) "
                            f"out of range [{lo}-{hi}] for '{part_name}'"
                        ),
                    ))
    return issues


def check_large_intervals(score: music21.stream.Score, plan: dict) -> list[ValidationIssue]:
    """Scan melody (first part) for intervals > 7 semitones.

    Note: music21 parses ABC 'c' as C5 (MIDI 72) while abc_to_midi.py maps
    'c' to C4 (MIDI 60). Relative intervals between consecutive notes are
    unaffected by this offset, but combining diacritical marks (U+0307/U+0323)
    used for octave indication may not be parsed correctly by music21,
    causing false positives. Threshold set to 7 semitones (a fifth) to
    reduce noise while still catching genuinely problematic leaps.
    """
    issues: list[ValidationIssue] = []
    if not score.parts:
        return issues

    melody_part = score.parts[0]
    voice_label = _voice_label(0)

    notes = list(melody_part.recurse().notes)
    for i in range(1, len(notes)):
        prev = notes[i - 1]
        curr = notes[i]
        # Handle Chord objects — use first pitch for interval calculation
        prev_pitch = prev.pitches[0] if hasattr(prev, 'pitches') else prev.pitch
        curr_pitch = curr.pitches[0] if hasattr(curr, 'pitches') else curr.pitch

        interval = music21.interval.Interval(prev_pitch, curr_pitch)
        if abs(interval.semitones) > 7:
            issues.append(ValidationIssue(
                category="large_interval",
                severity="warn",
                voice=voice_label,
                message=(
                    f"Large interval {abs(interval.semitones)} semitones "
                    f"({prev_pitch.nameWithOctave} -> {curr_pitch.nameWithOctave}) "
                    f"at measure {curr.measureNumber}"
                ),
            ))
    return issues


import re


def _parse_abc_measure_durations(
    abc_path: str, plan: dict,
) -> list[ValidationIssue]:
    """Parse ABC text directly and check measure durations.

    music21 auto-pads incomplete measures with rests, so we parse the
    raw ABC text and compute durations ourselves.
    """
    issues: list[ValidationIssue] = []

    ts_str = plan.get("time_signature", "4/4")
    try:
        num, den = ts_str.split("/")
        beats_per_measure = int(num)
    except (ValueError, ZeroDivisionError):
        beats_per_measure = 4

    text = Path(abc_path).read_text(encoding="utf-8")

    # Extract L: (default note length) — convert to quarter-note units
    # L:1/8 means an eighth note = 0.5 quarter notes
    default_length = 0.5  # default 1/8 note in quarter-note units
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("L:"):
            l_str = stripped[2:].strip()
            l_match = re.match(r"(\d+)/(\d+)", l_str)
            if l_match:
                # Convert from whole-note fraction to quarter-note units (* 4)
                default_length = 4.0 * int(l_match.group(1)) / int(l_match.group(2))
            break

    # Split into voice blocks
    voice_blocks = re.split(r"(^V:\d+.*$)", text, flags=re.MULTILINE)
    # voice_blocks: [header, V:1 line, body1, V:2 line, body2, ...]
    voice_idx = 0
    for i in range(1, len(voice_blocks), 2):
        v_line = voice_blocks[i]
        v_body = voice_blocks[i + 1] if i + 1 < len(voice_blocks) else ""

        voice_label_match = re.match(r"V:(\d+)", v_line)
        voice_label = f"V:{voice_label_match.group(1)}" if voice_label_match else f"V:{voice_idx + 1}"

        # Filter out directive lines (%%...) before splitting into measures
        v_body_filtered = "\n".join(
            line for line in v_body.splitlines()
            if not line.strip().startswith("%%")
        )

        # Normalize double bar lines and repeat-end markers to single bar lines
        v_body_filtered = v_body_filtered.replace("||", "|")

        # Split body into measures by | (excluding |: and :|)
        measures_raw = re.split(r"(?<![:\|])\|(?![\|:])", v_body_filtered)

        measure_num = 1
        for m_raw in measures_raw:
            m_raw = m_raw.strip()
            if not m_raw:
                continue

            # Remove repeat markers
            m_clean = re.sub(r"[:\|]", "", m_raw).strip()
            if not m_clean:
                continue

            # Calculate duration in beats (quarter notes = 1 beat)
            duration = _calc_abc_duration(m_clean, default_length)

            if abs(duration - beats_per_measure) > 0.01:
                issues.append(ValidationIssue(
                    category="measure_duration",
                    severity="fail",
                    voice=voice_label,
                    message=(
                        f"Measure {measure_num} duration "
                        f"{duration:.2f} beats, expected {beats_per_measure} beats "
                        f"(time signature {ts_str})"
                    ),
                ))
            measure_num += 1
        voice_idx += 1

    return issues


def _calc_abc_duration(tokens: str, default_length: float) -> float:
    """Calculate total duration of ABC note tokens in beats (quarter notes).

    Handles note names, rests (z/Z), chord brackets [...], and tuplets.
    Chords [FAc]4 are treated as a single unit with the chord's duration.
    """
    # Replace chord [notes]duration with a single rest of the same duration.
    # This ensures [F,A,c]4 counts as one unit (duration 4) instead of
    # summing individual note durations.
    tokens = re.sub(r"\[([^\]]*)\](\d*(?:/\d+)?)", r"z\2", tokens)

    # Remove ABC decorations (!xxx!) to prevent letters inside (e.g. f in !mf!)
    # from being parsed as note names.
    tokens = re.sub(r"![^!]*!", "", tokens)

    # Remove whitespace
    tokens = tokens.strip()

    if not tokens:
        return 0.0

    total = 0.0

    # Match individual note/rest tokens: [^_=/^]?[A-Ga-gzZ][,']*\d*/*\d*
    # Also handle ties (~)
    pattern = re.compile(r"([^A-Ga-gzZ~]*)([A-Ga-gzZ~])([,']*)(\d*(?:/\d+)?)")

    pos = 0
    while pos < len(tokens):
        m = pattern.match(tokens, pos)
        if not m:
            pos += 1
            continue

        prefix = m.group(1)
        note_char = m.group(2)
        octave_marks = m.group(3)
        duration_str = m.group(4)

        # Skip accidentals already consumed in prefix
        # Skip tie character
        if note_char == "~":
            pos = m.end()
            continue

        # Calculate note duration
        if duration_str:
            if "/" in duration_str:
                parts = duration_str.split("/")
                if parts[0]:
                    dur = int(parts[0]) / max(int(parts[1]), 1)
                else:
                    dur = 1.0 / max(int(parts[1]), 1)
            else:
                dur = int(duration_str)
        else:
            dur = 1  # multiplier

        note_duration = default_length * dur
        total += note_duration

        pos = m.end()

    return total


def check_measure_duration(score: music21.stream.Score, plan: dict, abc_path: str = "") -> list[ValidationIssue]:
    """Verify each measure sums to the expected beats from time signature."""
    if not abc_path:
        return []
    return _parse_abc_measure_durations(abc_path, plan)


def check_voice_alignment(score: music21.stream.Score, plan: dict) -> list[ValidationIssue]:
    """Check all voices have the same number of measures."""
    issues: list[ValidationIssue] = []

    if len(score.parts) < 2:
        return issues

    measure_counts: dict[str, int] = {}
    for idx, part in enumerate(score.parts):
        voice_label = _voice_label(idx)
        count = len(list(part.getElementsByClass("Measure")))
        measure_counts[voice_label] = count

    counts = list(measure_counts.values())
    if len(set(counts)) > 1:
        details = ", ".join(f"{v}: {c}" for v, c in sorted(measure_counts.items()))
        issues.append(ValidationIssue(
            category="voice_alignment",
            severity="fail",
            voice="global",
            message=f"Voices have different measure counts: {details}",
        ))
    return issues


def _parse_note_range(range_str) -> tuple[int, int]:
    """Parse a note range like 'D4-D6' or [60, 72] into (midi_lo, midi_hi).

    Accepts both string format ('D4-D6') and list format ([60, 72]).
    Returns (0, 127) for empty/missing values (e.g. drums).
    """
    if not range_str:
        return (0, 127)
    # Handle list format: [midi_lo, midi_hi]
    if isinstance(range_str, list):
        if len(range_str) == 2 and all(isinstance(v, (int, float)) for v in range_str):
            return (int(range_str[0]), int(range_str[1]))
        return (0, 127)
    # Handle string format: 'D4-D6'
    if not range_str.strip():
        return (0, 127)
    try:
        parts = range_str.strip().split('-')
        if len(parts) != 2:
            return (0, 127)
        lo = music21.pitch.Pitch(parts[0]).midi
        hi = music21.pitch.Pitch(parts[1]).midi
        return (lo, hi)
    except Exception:
        return (0, 127)


def check_voice_overlap(score: music21.stream.Score, plan: dict, abc_path: str = "") -> list[ValidationIssue]:
    """Check inter-voice register overlap and register compliance.

    Reads 'register' from plan orchestration (falls back to 'range').
    For each non-drum voice, checks:
    1. Actual pitch range vs target register (WARN if exceeded)
    2. Pairwise overlap between voices (>12 st = FAIL, >7 st = WARN)
    """
    issues: list[ValidationIssue] = []

    orch = plan.get("orchestration", {})
    if not orch:
        return issues

    # Map voice keys to their order: melody=0, harmony=1, bass=2, drums=3
    voice_order = ["melody", "harmony", "bass", "drums"]
    has_register = False

    # Build target register ranges from plan
    target_ranges: dict[int, tuple[int, int]] = {}
    for key in voice_order:
        entry = orch.get(key, {})
        if not entry:
            continue
        idx = voice_order.index(key)
        reg_str = entry.get("register", "")
        if reg_str:
            has_register = True
            target_ranges[idx] = _parse_note_range(reg_str)
        else:
            # Fallback to range field
            range_str = entry.get("range", "")
            target_ranges[idx] = _parse_note_range(range_str)

    if not has_register:
        issues.append(ValidationIssue(
            category="voice_overlap",
            severity="warn",
            voice="global",
            message="plan.json lacks register fields; using range as fallback for overlap check",
        ))

    # Compute actual pitch ranges per part
    actual_ranges: dict[int, tuple[int, int]] = {}
    for idx, part in enumerate(score.parts):
        midi_notes = []
        for note in part.recurse().notes:
            if hasattr(note, 'pitches'):
                midi_notes.extend(p.midi for p in note.pitches)
            else:
                midi_notes.append(note.pitch.midi)
        if midi_notes:
            actual_ranges[idx] = (min(midi_notes), max(midi_notes))

    # Check 1: actual range vs target register
    for idx in actual_ranges:
        if idx not in target_ranges:
            continue
        act_lo, act_hi = actual_ranges[idx]
        tgt_lo, tgt_hi = target_ranges[idx]
        if tgt_lo == 0 and tgt_hi == 127:
            # Drums or unmapped — skip
            continue
        voice_label = _voice_label(idx)
        below = max(0, tgt_lo - act_lo)
        above = max(0, act_hi - tgt_hi)
        if below > 0 or above > 0:
            parts = []
            if below > 0:
                parts.append(f"{below} semitones below")
            if above > 0:
                parts.append(f"{above} semitones above")
            issues.append(ValidationIssue(
                category="voice_overlap",
                severity="info",  # INFO: music21 octave mapping differs from abc_to_midi.py
                voice=voice_label,
                message=(
                    f"Actual range ({act_lo}-{act_hi}) exceeds target register "
                    f"({tgt_lo}-{tgt_hi}) by {' and '.join(parts)}"
                ),
            ))

    # Check 2: pairwise overlap between non-drum voices
    non_drum_parts = [idx for idx in actual_ranges if idx in target_ranges
                      and not (target_ranges[idx] == (0, 127))]
    for i in range(len(non_drum_parts)):
        for j in range(i + 1, len(non_drum_parts)):
            idx_a = non_drum_parts[i]
            idx_b = non_drum_parts[j]
            a_lo, a_hi = actual_ranges[idx_a]
            b_lo, b_hi = actual_ranges[idx_b]
            overlap_lo = max(a_lo, b_lo)
            overlap_hi = min(a_hi, b_hi)
            overlap = max(0, overlap_hi - overlap_lo)
            if overlap > 12:
                issues.append(ValidationIssue(
                    category="voice_overlap",
                    severity="warn",  # WARN: severe overlap still meaningful even with octave mismatch
                    voice="global",
                    message=(
                        f"{_voice_label(idx_a)} ({a_lo}-{a_hi}) and "
                        f"{_voice_label(idx_b)} ({b_lo}-{b_hi}) overlap "
                        f"by {overlap} semitones (>1 octave)"
                    ),
                ))
            elif overlap > 7:
                issues.append(ValidationIssue(
                    category="voice_overlap",
                    severity="info",  # INFO: music21 octave mapping differs from abc_to_midi.py
                    voice="global",
                    message=(
                        f"{_voice_label(idx_a)} ({a_lo}-{a_hi}) and "
                        f"{_voice_label(idx_b)} ({b_lo}-{b_hi}) overlap "
                        f"by {overlap} semitones (>5th)"
                    ),
                ))

    return issues


# ---------------------------------------------------------------------------
# check_sweet_spot (must be defined before CHECK_FUNCTIONS references it)
# ---------------------------------------------------------------------------

def check_sweet_spot(score: music21.stream.Score, plan: dict, abc_path: str = "") -> list[ValidationIssue] | None:
    """Check that most notes fall within the SF2 sweet_spot (WARN if < 60% coverage).

    Only runs when SF2 profile is loaded via --sf2-profile.
    Returns None (skip) if no profile is available.
    """
    if _sf2_profile is None:
        return None

    issues: list[ValidationIssue] = []

    voice_names = _parse_voice_names(abc_path) if abc_path else {}
    orchestration = plan.get("orchestration", {})
    voice_gm_map: dict[int, int | None] = {}
    for part_key, part_info in orchestration.items():
        voice_idx = {"melody": 1, "harmony": 2, "bass": 3, "drums": 4}.get(part_key)
        if voice_idx:
            voice_gm_map[voice_idx] = part_info.get("instrument")

    for idx, part in enumerate(score.parts):
        voice_label = _voice_label(idx)
        voice_id = idx + 1
        gm_inst = voice_gm_map.get(voice_id)
        if gm_inst is None:
            continue

        preset = _sf2_profile.get("presets", {}).get(str(gm_inst))
        if not preset or "sweet_spot" not in preset:
            continue

        ss_lo, ss_hi = preset["sweet_spot"]
        total_notes = 0
        in_spot = 0

        for note in part.recurse().notes:
            pitches = note.pitches if hasattr(note, 'pitches') else [note.pitch]
            for p in pitches:
                total_notes += 1
                if ss_lo <= p.midi <= ss_hi:
                    in_spot += 1

        if total_notes == 0:
            continue

        ratio = in_spot / total_notes
        if ratio < 0.6:
            part_name = voice_names.get(voice_id, f"V:{voice_id}")
            issues.append(ValidationIssue(
                category="sweet_spot",
                severity="warn",
                voice=voice_label,
                message=(
                    f"Only {ratio:.0%} of notes in sweet_spot "
                    f"[{ss_lo}-{ss_hi}] for '{part_name}' "
                    f"(GM#{gm_inst}, {ratio:.0%} < 60%)"
                ),
            ))

    return issues if issues else None


# ---------------------------------------------------------------------------
# Main validate function
# ---------------------------------------------------------------------------

CHECK_FUNCTIONS = [
    ("key_consistency", check_key_consistency),
    ("pitch_range", check_pitch_range),
    ("voice_overlap", check_voice_overlap),
    ("large_interval", check_large_intervals),
    ("measure_duration", check_measure_duration),
    ("voice_alignment", check_voice_alignment),
    ("sweet_spot", check_sweet_spot),
]


def validate(abc_path: str, plan_path: str) -> ValidationReport:
    """Run all validation checks on an ABC file against a plan.

    Args:
        abc_path: Path to the ABC file.
        plan_path: Path to the plan JSON file.

    Returns:
        ValidationReport with fails, warns, and passes.
    """
    plan = _load_plan(plan_path)
    score = _parse_abc(abc_path)

    fails: list[ValidationIssue] = []
    warns: list[ValidationIssue] = []
    infos: list[ValidationIssue] = []
    passes: list[str] = []

    for category_name, check_fn in CHECK_FUNCTIONS:
        try:
            result = check_fn(score, plan, abc_path=abc_path)
        except TypeError:
            # Fallback for functions without abc_path parameter
            try:
                result = check_fn(score, plan)
            except Exception as exc:
                fails.append(ValidationIssue(
                    category=category_name,
                    severity="fail",
                    voice="global",
                    message=f"Check raised exception: {exc}",
                ))
                continue
        except Exception as exc:
            fails.append(ValidationIssue(
                category=category_name,
                severity="fail",
                voice="global",
                message=f"Check raised exception: {exc}",
            ))
            continue

        if result is None:
            passes.append(category_name)
        elif isinstance(result, list):
            if not result:
                passes.append(category_name)
            else:
                for issue in result:
                    if issue.severity == "fail":
                        fails.append(issue)
                    elif issue.severity == "info":
                        infos.append(issue)
                    else:
                        warns.append(issue)
        elif isinstance(result, ValidationIssue):
            if result.severity == "fail":
                fails.append(result)
            elif result.severity == "info":
                infos.append(result)
            else:
                warns.append(result)

    return ValidationReport(fails=fails, warns=warns, passes=passes, infos=infos)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    global _sf2_profile

    if len(sys.argv) < 3:
        print("Usage: python validate_abc.py <file.abc> <plan.json> [--json output.json] [--sf2-profile profile.json]")
        sys.exit(2)

    abc_path = sys.argv[1]
    plan_path = sys.argv[2]
    json_output = None
    sf2_profile_path = None

    if "--json" in sys.argv:
        idx = sys.argv.index("--json")
        if idx + 1 < len(sys.argv):
            json_output = sys.argv[idx + 1]

    if "--sf2-profile" in sys.argv:
        idx = sys.argv.index("--sf2-profile")
        if idx + 1 < len(sys.argv):
            sf2_profile_path = sys.argv[idx + 1]
            with open(sf2_profile_path, "r", encoding="utf-8") as f:
                _sf2_profile = json.load(f)

    report = validate(abc_path, plan_path)
    print(str(report))

    if json_output:
        report.to_json(json_output)
        print(f"\nReport written to {json_output}")

    if report.fails:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
