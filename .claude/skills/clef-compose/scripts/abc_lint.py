#!/usr/bin/env python3
"""ABC Linter — deterministic pre-merge checks for forbidden patterns.

Runs as a fast gate before merge_abc.py to catch patterns that LLM agents
repeatedly produce despite prompt instructions. Zero dependencies (no music21).

Checks:
  1. Natural signs (=) that cancel key signature modifications
  2. %% directives containing V: (phantom voice declarations)
  3. || double barlines in music content
  4. Measure duration mismatch (per-voice, per-measure)
  5. Register compliance (notes outside plan.json target register)

Usage:
  python abc_lint.py <file.abc>               # lint only, exit 1 if issues
  python abc_lint.py <file.abc> --fix          # auto-fix safe patterns + lint
  python abc_lint.py <file.abc> --plan plan.json # include register check
  python abc_lint.py <file.abc> --json         # output as JSON

Exit codes: 0=pass, 1=issues found
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Key signature lookup: key name → set of note names modified by the signature
# E.g. K:Dm → {"B"} means B is flattened to Bb by the key signature.
# ---------------------------------------------------------------------------

KEY_SIGNATURES: dict[str, set[str]] = {
    # Major keys
    "C": set(), "G": {"F"}, "D": {"F", "C"}, "A": {"F", "C", "G"},
    "E": {"F", "C", "G", "D"}, "B": {"F", "C", "G", "D", "A"},
    "F#": {"F", "C", "G", "D", "A", "E"}, "Gb": {"B", "E", "A", "D", "G", "C"},
    "F": {"B"}, "Bb": {"B", "E"}, "Eb": {"B", "E", "A"},
    "Ab": {"B", "E", "A", "D"}, "Db": {"B", "E", "A", "D", "G"},
    "Cb": {"B", "E", "A", "D", "G", "C"},
    # Minor keys
    "Am": set(), "Em": {"F"}, "Bm": {"F", "C"}, "F#m": {"F", "C", "G"},
    "C#m": {"F", "C", "G", "D"}, "G#m": {"F", "C", "G", "D", "A"},
    "D#m": {"F", "C", "G", "D", "A", "E"}, "A#m": {"F", "C", "G", "D", "A", "E", "B"},
    "Dm": {"B"}, "Gm": {"B", "E"}, "Cm": {"B", "E", "A"},
    "Fm": {"B", "E", "A", "D"}, "Bbm": {"B", "E", "A", "D", "G"},
    "Ebm": {"B", "E", "A", "D", "G", "C"},
}

# Note names that have sharps in key signatures
_SHARP_KEYS = {"G", "D", "A", "E", "B", "F#", "Em", "Bm", "F#m", "C#m", "G#m", "D#m", "A#m"}
_FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm"}

# Regex for ABC header fields: a single letter followed by ':'
_ABC_HEADER_RE = re.compile(r'^[A-Za-z]\s*:')

# ABC note → MIDI pitch mapping (matches abc_to_midi.py NOTE_PITCH)
_NOTE_PITCH = {
    'c': 60, 'd': 62, 'e': 64, 'f': 65, 'g': 67, 'a': 69, 'b': 71,
    'C': 48, 'D': 50, 'E': 52, 'F': 53, 'G': 55, 'A': 57, 'B': 59,
}

# Regex for individual note/rest tokens: prefix + note + octave + duration
_NOTE_TOKEN_RE = re.compile(
    r"([^A-Ga-gzZ~]*)([A-Ga-gzZ~])([,']*)(\d*(?:/\d+)?)"
)


def _is_header_or_comment(line: str) -> bool:
    """Return True if line is an ABC header field, directive, or comment."""
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith('%') or stripped.startswith('%%'):
        return True
    if _ABC_HEADER_RE.match(stripped):
        return True
    return False


def _normalize_key(raw_key: str) -> str:
    """Normalize ABC key name to lookup table key.

    'Dmin'/'Dminor' → 'Dm', 'Dmaj'/'Dmajor' → 'D', 'F#' stays 'F#'.
    """
    k = raw_key.strip()
    # Order matters: check longer suffixes first
    if k.endswith('minor'):
        return k[:-5] + 'm'
    if k.endswith('major'):
        return k[:-5]
    if k.endswith('min'):
        return k[:-3] + 'm'
    if k.endswith('maj'):
        return k[:-3]
    return k


def parse_key(abc_content: str) -> str:
    """Extract key name from ABC K: field, normalized for lookup."""
    for line in abc_content.splitlines():
        m = re.match(r'^K:\s*(.+)', line.strip())
        if m:
            return _normalize_key(m.group(1).strip())
    return "C"


def check_natural_signs(abc_content: str, key_name: str) -> list[dict]:
    """Check for = (natural) signs that cancel key signature modifications.

    In K:Dm, B is already Bb. Writing =B makes it B natural, which is
    almost always an error when the agent meant to write Bb (just write B).
    """
    modified_notes = KEY_SIGNATURES.get(key_name, set())
    if not modified_notes:
        return []

    is_sharp_key = key_name in _SHARP_KEYS
    modifier_word = "sharpened" if is_sharp_key else "flattened"

    issues = []
    for i, line in enumerate(abc_content.splitlines(), 1):
        if _is_header_or_comment(line):
            continue

        for match in re.finditer(r'=\s*([A-Ga-g])', line):
            note = match.group(1).upper()
            if note in modified_notes:
                issues.append({
                    "line": i,
                    "rule": "natural_cancels_key_signature",
                    "severity": "warn",
                    "message": (
                        f"Line {i}: ={note} cancels key signature "
                        f"({modifier_word} in K:{key_name}). "
                        f"If you mean the key's default, write '{note}' without '='."
                    ),
                })

    return issues


def check_phantom_voice_directives(abc_content: str) -> list[dict]:
    """Check for %% directives that contain V: declarations.

    Lines like '%% V:3 低音' can be parsed as a new voice declaration,
    creating phantom voices that break measure alignment.
    """
    issues = []
    for i, line in enumerate(abc_content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('%%') and re.search(r'V:\d+', stripped):
            # Allow legitimate %%MIDI directives
            if '%%MIDI' in stripped:
                continue
            issues.append({
                "line": i,
                "rule": "phantom_voice_directive",
                "severity": "warn",
                "message": (
                    f"Line {i}: '%%' directive contains 'V:' which may be "
                    f"parsed as voice declaration. Use '%' for comments."
                ),
            })

    return issues


def check_double_barlines(abc_content: str) -> list[dict]:
    """Check for || double barlines in music content.

    Double barlines can cause extra empty measures in some parsers.
    """
    issues = []
    for i, line in enumerate(abc_content.splitlines(), 1):
        if _is_header_or_comment(line):
            continue
        if '||' in line:
            issues.append({
                "line": i,
                "rule": "double_barline",
                "severity": "warn",
                "message": f"Line {i}: '||' double barline may cause extra measures. Use '|'.",
            })

    return issues


# ---------------------------------------------------------------------------
# Check 4: Measure duration mismatch
# ---------------------------------------------------------------------------

def _parse_abc_header(abc_content: str) -> tuple[float, float]:
    """Extract L: (default note length) and M: (beats per measure) from ABC.

    Returns (default_length, beats_per_measure) in quarter-note units.
    L:1/8 → default_length=0.5, M:4/4 → beats_per_measure=4.0.
    """
    default_length = 0.5  # L:1/8 in quarter-note units
    beats_per_measure = 4.0

    for line in abc_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("L:"):
            m = re.match(r"(\d+)/(\d+)", stripped[2:].strip())
            if m:
                default_length = 4.0 * int(m.group(1)) / int(m.group(2))
        elif stripped.startswith("M:"):
            m = re.match(r"(\d+)/(\d+)", stripped[2:].strip())
            if m:
                beats_per_measure = float(int(m.group(1)))

    return default_length, beats_per_measure


def _calc_abc_duration(tokens: str, default_length: float) -> float:
    """Calculate total duration of ABC note tokens in beats (quarter notes).

    Ported from validate_abc.py._calc_abc_duration (zero-dependency version).
    Handles note names, rests (z/Z), chord brackets [...], and ties (~).
    """
    # Replace chords [notes]duration with a single rest of same duration
    tokens = re.sub(r"\[([^\]]*)\](\d*(?:/\d+)?)", r"z\2", tokens)
    # Remove decorations and chord annotations
    tokens = re.sub(r"![^!]*!", "", tokens)
    tokens = re.sub(r'"[^"]*"', "", tokens)
    tokens = tokens.strip()

    if not tokens:
        return 0.0

    total = 0.0
    pos = 0
    while pos < len(tokens):
        m = _NOTE_TOKEN_RE.match(tokens, pos)
        if not m:
            pos += 1
            continue

        note_char = m.group(2)
        duration_str = m.group(4)

        if note_char == "~":  # tie
            pos = m.end()
            continue

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
            dur = 1

        total += default_length * dur
        pos = m.end()

    return total


def check_measure_durations(abc_content: str) -> list[dict]:
    """Check per-voice per-measure duration matches the time signature.

    Splits voice blocks by V: lines, then splits each block into measures
    by | barlines. Reports any measure whose duration doesn't match M:/L:.
    """
    default_length, beats_per_measure = _parse_abc_header(abc_content)

    issues = []
    voice_blocks = re.split(r"(^V:\d+.*$)", abc_content, flags=re.MULTILINE)

    for i in range(1, len(voice_blocks), 2):
        v_line = voice_blocks[i]
        v_body = voice_blocks[i + 1] if i + 1 < len(voice_blocks) else ""

        voice_match = re.match(r"V:(\d+)", v_line)
        voice_label = f"V:{voice_match.group(1)}" if voice_match else "V:?"

        # Skip percussion voices (known parsing artifact)
        if re.search(r"clef=perc", v_line):
            continue

        # Filter directives and normalize barlines
        v_body_filtered = "\n".join(
            line for line in v_body.splitlines()
            if not line.strip().startswith("%%")
        )
        v_body_filtered = v_body_filtered.replace("||", "|")

        # Split into measures by | (excluding |: and :| and |])
        measures_raw = re.split(r"(?<![:\|])\|(?![\|:\]])", v_body_filtered)

        measure_num = 1
        for m_raw in measures_raw:
            m_raw = m_raw.strip()
            if not m_raw:
                continue

            m_clean = re.sub(r"[:\|]", "", m_raw).strip()
            if not m_clean:
                continue

            duration = _calc_abc_duration(m_clean, default_length)

            if abs(duration - beats_per_measure) > 0.01:
                issues.append({
                    "line": 0,
                    "rule": "measure_duration",
                    "severity": "warn",
                    "message": (
                        f"{voice_label} m{measure_num}: duration "
                        f"{duration:.2f} beats, expected {beats_per_measure:.0f} beats"
                    ),
                })
            measure_num += 1

    return issues


# ---------------------------------------------------------------------------
# Check 5: Register compliance (notes outside plan.json target register)
# ---------------------------------------------------------------------------

def _abc_note_to_midi(note_token: str) -> int | None:
    """Convert a single ABC note token to MIDI pitch number.

    Returns None for rests (z/Z), ties (~), or unparseable tokens.
    Handles accidentals (_, ^, =) and octave marks (, ').
    """
    if not note_token:
        return None

    m = re.match(r"([_^=]*)([A-Ga-gzZ~])([,']*)", note_token)
    if not m:
        return None

    accidentals = m.group(1)
    note_char = m.group(2)
    octave_marks = m.group(3)

    if note_char in "zZ~":
        return None

    base = _NOTE_PITCH.get(note_char)
    if base is None:
        return None

    # Accidentals: ^^ = +2, __ = -2, ^ = +1, _ = -1, = = 0 (natural)
    if accidentals.startswith("^^"):
        accidental_shift = 2
    elif accidentals.startswith("__"):
        accidental_shift = -2
    elif "^" in accidentals:
        accidental_shift = 1
    elif "_" in accidentals:
        accidental_shift = -1
    else:
        accidental_shift = 0

    # Octave: each , = -12, each ' = +12
    octave_shift = 0
    for ch in octave_marks:
        if ch == ",":
            octave_shift -= 12
        elif ch == "'":
            octave_shift += 12

    return base + accidental_shift + octave_shift


def check_register(abc_content: str, plan: dict) -> list[dict]:
    """Check that all notes fall within plan.json orchestration register ranges.

    Uses the 'register' field (not 'range') from each voice's sf2 config.
    Skips percussion voices (V:4 / clef=perc).
    """
    issues = []
    orchestration = plan.get("orchestration", {})

    # Build voice_id → register map from plan.json
    # orchestration keys: melody, harmony, bass, drums
    voice_registers: dict[str, tuple[int, int]] = {}
    voice_names = {"melody": "1", "harmony": "2", "bass": "3", "drums": "4"}
    for part_key, part_info in orchestration.items():
        vid = voice_names.get(part_key)
        if not vid:
            continue
        sf2 = part_info.get("sf2") or {}
        reg = sf2.get("register")
        if reg and len(reg) == 2:
            voice_registers[f"V:{vid}"] = (int(reg[0]), int(reg[1]))

    if not voice_registers:
        return issues

    voice_blocks = re.split(r"(^V:\d+.*$)", abc_content, flags=re.MULTILINE)

    for i in range(1, len(voice_blocks), 2):
        v_line = voice_blocks[i]
        v_body = voice_blocks[i + 1] if i + 1 < len(voice_blocks) else ""

        voice_match = re.match(r"V:(\d+)", v_line)
        voice_label = f"V:{voice_match.group(1)}" if voice_match else "V:?"

        # Skip percussion
        if re.search(r"clef=perc", v_line):
            continue

        if voice_label not in voice_registers:
            continue

        lo, hi = voice_registers[voice_label]

        # Tokenize and check each note
        for line in v_body.splitlines():
            if _is_header_or_comment(line):
                continue

            for token_match in re.finditer(
                r"[_^=]*[A-Ga-g][,']*\d*(?:/\d+)?", line
            ):
                token = token_match.group()
                # Strip duration suffix for MIDI conversion
                note_only = re.sub(r"\d/(?:\d+)?$", "", token)
                note_only = re.sub(r"\d+$", "", note_only)

                midi = _abc_note_to_midi(note_only)
                if midi is None:
                    continue

                if midi < lo or midi > hi:
                    direction = "below" if midi < lo else "above"
                    issues.append({
                        "line": 0,
                        "rule": "register_violation",
                        "severity": "warn",
                        "message": (
                            f"{voice_label}: MIDI {midi} ({direction} register "
                            f"{lo}-{hi}), note '{token}'"
                        ),
                    })

    return issues


def lint(abc_content: str, plan: dict | None = None) -> dict:
    """Run all lint checks on ABC content.

    Checks 1-3 run always (zero-dependency).
    Check 4 (measure duration) runs always.
    Check 5 (register compliance) requires plan.json with orchestration.register.
    """
    key_name = parse_key(abc_content)

    all_issues = []
    all_issues.extend(check_natural_signs(abc_content, key_name))
    all_issues.extend(check_phantom_voice_directives(abc_content))
    all_issues.extend(check_double_barlines(abc_content))
    all_issues.extend(check_measure_durations(abc_content))

    if plan is not None:
        all_issues.extend(check_register(abc_content, plan))

    return {
        "key": key_name,
        "total_issues": len(all_issues),
        "issues": all_issues,
        "pass": len(all_issues) == 0,
    }


def sanitize(abc_content: str) -> str:
    """Auto-fix safe patterns in ABC content.

    1. || → | in music lines (double barlines to single)
    2. %% V:X comments → % V:X (phantom voice directives)

    Returns the sanitized content. Lines with other modifications are left intact.
    """
    lines = abc_content.splitlines()
    fixed = []

    for line in lines:
        # Fix double barlines in music content (not header/directive lines)
        if not _is_header_or_comment(line):
            line = line.replace('||', '|')

        # Fix %% V: comments (not %%MIDI directives)
        stripped = line.strip()
        if stripped.startswith('%%') and re.search(r'V:\d+', stripped) and '%%MIDI' not in stripped:
            line = line.replace('%%', '%', 1)

        fixed.append(line)

    return '\n'.join(fixed)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python abc_lint.py <file.abc> [--fix] [--json] [--plan plan.json]",
              file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]
    do_fix = '--fix' in sys.argv
    do_json = '--json' in sys.argv

    plan = None
    plan_idx = sys.argv.index('--plan') if '--plan' in sys.argv else -1
    if plan_idx >= 0 and plan_idx + 1 < len(sys.argv):
        with open(sys.argv[plan_idx + 1], 'r', encoding='utf-8') as f:
            plan = json.load(f)

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if do_fix:
        original = content
        content = sanitize(content)
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            if not do_json:
                print(f"Fixed: {filepath}")

    result = lint(content, plan=plan)

    if do_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["pass"]:
            print(f"OK (K:{result['key']}, 0 issues)")
        else:
            for issue in result["issues"]:
                print(f"  {issue['severity'].upper()} [{issue['rule']}] {issue['message']}")
            print(f"\n{result['total_issues']} issue(s) found")

    sys.exit(0 if result["pass"] else 1)
