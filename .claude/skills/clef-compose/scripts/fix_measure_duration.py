#!/usr/bin/env python3
"""Deterministic fix for ABC measure duration errors.

Mechanically adjusts the last note/rest in each measure when off by 1-2 units.
Measures off by >2 units are skipped (left for Revision agent).

Ported from server/src/clef_server/tools.py for use in Claude Code workflow.

Usage:
    python fix_measure_duration.py <input.abc> [-o <output.abc>] [--max-deviation 2.0]
    python fix_measure_duration.py <input.abc> --stdin  # read ABC from stdin
"""

import argparse
import json
import re
import sys
from pathlib import Path


# === Regex patterns ===

_NOTE_RE = re.compile(
    r"([\\^_=]*"           # accidental
    r"[a-gA-G]"            # note name
    r"[',]*"               # octave marks
    r")"
    r"(\d*(?:/\d+)?)"      # duration: "2", "3", "/2", "3/2", or "" (=1)
)
_REST_RE = re.compile(r"(z)(\d*(?:/\d+)?)")
_CHORD_RE = re.compile(r"(\[[^\]]+\])(\d*(?:/\d+)?)")
_TUPLET_RE = re.compile(r"\((\d+)")


# === Core helpers ===

def _parse_abc_duration(duration_str: str) -> float:
    """Convert ABC duration string to float units.

    "" -> 1.0, "2" -> 2.0, "/2" -> 0.5, "3/2" -> 1.5
    """
    if not duration_str:
        return 1.0
    if "/" in duration_str:
        parts = duration_str.split("/")
        num = int(parts[0]) if parts[0] else 1
        den = int(parts[1])
        return num / den
    return float(duration_str)


def _duration_to_str(units: float) -> str:
    """Convert float units back to ABC duration string."""
    if units == 1.0:
        return ""
    if units == int(units):
        return str(int(units))
    for den in (2, 3, 4, 8):
        if abs(units * den - round(units * den)) < 0.01:
            num = int(round(units * den))
            if num == 1:
                return f"/{den}"
            return f"{num}/{den}"
    return str(units)


def _count_measure_units(measure_text: str) -> float:
    """Count total duration units in a measure, handling chords and tuplets."""
    text = measure_text.strip()
    events: list[tuple[int, int, float]] = []

    for m in _CHORD_RE.finditer(text):
        dur = _parse_abc_duration(m.group(2))
        events.append((m.start(), m.end(), dur))

    for m in _REST_RE.finditer(text):
        dur = _parse_abc_duration(m.group(2))
        events.append((m.start(), m.end(), dur))

    chord_ranges = [(e[0], e[1]) for e in events]
    for m in _NOTE_RE.finditer(text):
        inside_chord = any(cs <= m.start() < ce for cs, ce in chord_ranges)
        if not inside_chord:
            dur = _parse_abc_duration(m.group(2))
            events.append((m.start(), m.end(), dur))

    events.sort(key=lambda e: e[0])

    # Apply tuplet ratio
    for m in _TUPLET_RE.finditer(text):
        ratio = int(m.group(1))
        tuplet_end_pos = m.end()
        affected: list[int] = []
        for i, (start, end, dur) in enumerate(events):
            if start >= tuplet_end_pos and len(affected) < ratio:
                affected.append(i)
        if affected:
            factor = (ratio - 1) / ratio if ratio > 1 else 1.0
            for i in affected:
                s, e, d = events[i]
                events[i] = (s, e, d * factor)

    return sum(e[2] for e in events)


def _fix_single_measure(
    measure_text: str,
    target: float,
    max_deviation: float = 2.0,
) -> tuple[str, dict | None]:
    """Try to fix a single measure by adjusting the last note/rest."""
    actual = _count_measure_units(measure_text)
    diff = actual - target

    if abs(diff) < 0.01:
        return measure_text, None

    if abs(diff) > max_deviation + 0.01:
        return measure_text, {"skipped": True, "actual_units": actual, "target_units": target}

    text = measure_text
    all_events: list[tuple[int, int, str, str]] = []

    for m in _CHORD_RE.finditer(text):
        all_events.append((m.start(), m.end(), m.group(1), m.group(2)))
    for m in _REST_RE.finditer(text):
        all_events.append((m.start(), m.end(), m.group(1), m.group(2)))
    chord_ranges = [(e[0], e[1]) for e in all_events]
    for m in _NOTE_RE.finditer(text):
        inside_chord = any(cs <= m.start() < ce for cs, ce in chord_ranges)
        if not inside_chord:
            all_events.append((m.start(), m.end(), m.group(1), m.group(2)))

    if not all_events:
        return measure_text, {"skipped": True, "actual_units": actual, "target_units": target}

    all_events.sort(key=lambda e: e[0])
    last_start, last_end, last_prefix, last_dur_str = all_events[-1]
    last_dur = _parse_abc_duration(last_dur_str)
    new_dur = last_dur - diff

    if new_dur < 0.01:
        before = text[:last_start].rstrip()
        fixed = before + text[last_end:]
        target_type = "rest" if last_prefix == "z" else ("chord" if last_prefix.startswith("[") else "note")
        return fixed, {
            "action": "remove", "target": target_type,
            "from": text[last_start:last_end], "to": "(removed)",
            "actual_units": actual, "target_units": target,
        }

    new_dur_str = _duration_to_str(new_dur)
    old_event = text[last_start:last_end]
    new_event = last_prefix + new_dur_str
    fixed = text[:last_start] + new_event + text[last_end:]

    action = "shorten" if diff > 0 else "extend"
    target_type = "rest" if last_prefix == "z" else ("chord" if last_prefix.startswith("[") else "note")

    return fixed, {
        "action": action, "target": target_type,
        "from": old_event, "to": new_event,
        "actual_units": actual, "target_units": target,
    }


# === Main logic ===

def fix_abc_content(
    abc_content: str,
    max_deviation: float = 2.0,
) -> dict:
    """Fix measure duration errors in ABC content.

    Returns dict with keys: abc, fixes, passed, measures_checked.
    """
    lines = abc_content.split("\n")

    # Parse headers for M: and L:
    m_match = None
    l_base = 4
    header_end = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("M:"):
            m_match = re.match(r"M:(\d+)/(\d+)", stripped)
        elif stripped.startswith("L:"):
            l_match = re.match(r"L:1/(\d+)", stripped)
            if l_match:
                l_base = int(l_match.group(1))
        elif stripped.startswith("K:"):
            header_end = i + 1
            break

    # Auto-detect target
    if m_match:
        num = int(m_match.group(1))
        den = int(m_match.group(2))
        target_per_measure = num * l_base / den
    else:
        target_per_measure = 4.0

    fixes: list[dict] = []
    passed = True
    measures_checked = 0
    result_lines: list[str] = []

    for i, line in enumerate(lines):
        if "|" not in line or i < header_end:
            result_lines.append(line)
            continue
        if line.strip().startswith("%%"):
            result_lines.append(line)
            continue

        parts = line.split("|")
        fixed_parts: list[str] = []

        for j, part in enumerate(parts):
            stripped_part = part.strip()
            if not stripped_part:
                fixed_parts.append(part)
                continue
            if stripped_part.startswith("V:") or stripped_part.startswith("%"):
                fixed_parts.append(part)
                continue

            measures_checked += 1
            fixed_text, fix_info = _fix_single_measure(stripped_part, target_per_measure, max_deviation)

            if fix_info is not None:
                passed = False
                fixes.append({"measure": measures_checked, **fix_info})
                if not fix_info.get("skipped"):
                    leading = part[:len(part) - len(part.lstrip())]
                    trailing = part[len(part.rstrip()):]
                    fixed_parts.append(leading + fixed_text + trailing)
                else:
                    fixed_parts.append(part)
            else:
                fixed_parts.append(part)

        result_lines.append("|".join(fixed_parts))

    return {
        "abc": "\n".join(result_lines),
        "fixes": fixes,
        "passed": passed,
        "measures_checked": measures_checked,
    }


def main():
    parser = argparse.ArgumentParser(description="Fix ABC measure duration errors")
    parser.add_argument("input", help="Input ABC file path")
    parser.add_argument("-o", "--output", help="Output ABC file path (default: overwrite input)")
    parser.add_argument("--max-deviation", type=float, default=2.0,
                        help="Max deviation to fix mechanically (default: 2.0)")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    abc_content = input_path.read_text(encoding="utf-8")
    result = fix_abc_content(abc_content, args.max_deviation)

    output_path = Path(args.output) if args.output else input_path
    output_path.write_text(result["abc"], encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        fixes = result["fixes"]
        measures_checked = result["measures_checked"]
        if not fixes:
            print(f"All {measures_checked} measures OK, no fixes needed.")
        else:
            fixed_count = sum(1 for f in fixes if not f.get("skipped"))
            skipped_count = sum(1 for f in fixes if f.get("skipped"))
            print(f"Checked {measures_checked} measures: {fixed_count} fixed, {skipped_count} skipped")
            for f in fixes:
                if f.get("skipped"):
                    print(f"  Measure {f['measure']}: SKIPPED (off by {abs(f['actual_units'] - f['target_units']):.1f} units, too large)")
                else:
                    print(f"  Measure {f['measure']}: {f['action']} {f['target']} {f['from']} -> {f['to']}")
        if result["passed"]:
            print("PASS: all measures have correct duration.")
        else:
            print("FAIL: some measures could not be fixed (left for Revision agent).")


if __name__ == "__main__":
    main()
