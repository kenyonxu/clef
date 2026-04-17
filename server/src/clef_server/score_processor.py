"""Pure functions for ABC/MIDI score manipulation."""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Voice label to agent name mapping
VOICE_TO_AGENT = {
    "V:1": "clef-composer",
    "V:2": "clef-harmonist",
    "V:3": "clef-rhythmist",
    "V:4": "clef-rhythmist",
}

_BAR_RE = re.compile(r'(?<![\|:])\|(?![\|:])')


def stamp_agent_meta(content: str, agent: str, voice: str, round_num: int) -> str:
    """Inject % ClefMeta comment at top of ABC content."""
    meta = json.dumps({
        "agent": agent,
        "voice": voice,
        "round": round_num,
        "timestamp": time.time(),
    }, ensure_ascii=False)
    return f"% ClefMeta: {meta}\n{content}"


def inject_midi_programs(score_path: Path, plan: dict) -> None:
    """Inject %%MIDI program directives into score.abc based on plan.json.

    Maps each voice (V:1..V:4) to its orchestration part and injects
    the midi_program number. Skips voices that already have a program directive.
    """
    orch = plan.get("orchestration", {})
    voice_map = {
        1: orch.get("melody", {}),
        2: orch.get("harmony", {}),
        3: orch.get("bass", {}),
        4: orch.get("drums", {}),
    }

    text = score_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    new_lines: list[str] = []
    injected_voices: set[int] = set()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("%%MIDI program"):
            continue
        new_lines.append(line)
        for voice_num, part in voice_map.items():
            if stripped == f"V:{voice_num}" and voice_num not in injected_voices:
                prog = part.get("midi_program")
                if prog is not None:
                    new_lines.append(f"%%MIDI program {prog}")
                    injected_voices.add(voice_num)

    score_path.write_text("\n".join(new_lines), encoding="utf-8")


def apply_duration_constraint(plan: dict, user_prompt: str) -> dict:
    """If the user prompt specifies a duration, override total_bars and redistribute sections.

    Supports patterns like "45秒", "30秒左右", "1分钟", "1分30秒", "90s".
    """
    # Extract duration in seconds from prompt
    seconds = 0.0
    # Match "X分Y秒" or "X分钟Y秒"
    m = re.search(r"(\d+)\s*(?:分|分钟)\s*(?:(\d+)\s*秒)?", user_prompt)
    if m:
        seconds = int(m.group(1)) * 60
        if m.group(2):
            seconds += int(m.group(2))
    else:
        # Match "X秒" or "Xs"
        m = re.search(r"(\d+)\s*(?:秒|s)", user_prompt)
        if m:
            seconds = float(m.group(1))

    if seconds <= 0:
        return plan

    bpm = plan.get("bpm", 120)
    ts = plan.get("time_signature", "4/4")
    beats_per_bar = float(ts.split("/")[0]) if "/" in ts else 4.0
    target_bars = round(seconds * bpm / 60.0 / beats_per_bar)
    target_bars = max(8, target_bars)  # minimum 8 bars

    if target_bars == plan.get("total_bars"):
        return plan

    logger.info(
        "Duration constraint: user wants ~%.0fs, adjusting total_bars %d → %d (bpm=%d, %s)",
        seconds, plan.get("total_bars"), target_bars, bpm, ts,
    )

    # Redistribute sections proportionally
    sections = plan.get("sections", [])
    if not sections:
        return plan

    old_total = sum(s.get("measures", 1) for s in sections)
    remaining = target_bars
    for i, sec in enumerate(sections):
        if i == len(sections) - 1:
            sec["measures"] = max(2, remaining)
        else:
            ratio = sec.get("measures", 1) / max(old_total, 1)
            new_measures = max(2, round(ratio * target_bars))
            sec["measures"] = new_measures
            remaining -= new_measures

    plan["total_bars"] = target_bars
    return plan


def trim_trailing_rests(abc_text: str) -> str:
    """Remove trailing rest-only bars from ABC voice content.

    Detects lines consisting solely of rests (z2, z4, z8, etc.) and bars (|)
    at the end of the text and strips them.
    """
    lines = abc_text.rstrip().split("\n")
    # Work backwards, find last non-rest line index (immutable)
    last_non_rest = len(lines)
    while last_non_rest > 0:
        stripped = lines[last_non_rest - 1].strip()
        if re.match(r'^[\s|z\d/]*$', stripped) and 'z' in stripped:
            last_non_rest -= 1
        else:
            break
    return "\n".join(lines[:last_non_rest])


def calculate_demo_bars(total_bars: int) -> int:
    """Calculate demo_length_bars as ~30% of total_bars, clamped to [8, 64]."""
    if total_bars <= 0:
        return 8
    return max(8, min(64, round(total_bars * 0.3)))


def parse_voice_blocks(score_text: str) -> dict[str, str]:
    """Extract voice blocks from a merged score.abc.

    Returns {"V:1": "C D E F|...", "V:2": "[FAc] ...", ...}
    """
    blocks: dict[str, str] = {}
    lines = score_text.split("\n")
    current_voice: str | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        voice_match = re.match(r'^(V:\d[\+\d]*)', stripped)
        if voice_match:
            if current_voice and current_lines:
                blocks[current_voice] = "\n".join(current_lines).strip()
            current_voice = voice_match.group(1)
            current_lines = []
        elif current_voice:
            current_lines.append(line)

    if current_voice and current_lines:
        blocks[current_voice] = "\n".join(current_lines).strip()

    return blocks


def count_bars(abc_text: str) -> int:
    """Count bar lines (|) in ABC text, excluding ||, |:, and :|."""
    count = 0
    for line in abc_text.strip().split("\n"):
        stripped = line.strip()
        if stripped.startswith("%"):
            continue
        count += len(_BAR_RE.findall(stripped))
    return count


def truncate_to_bars(abc_text: str, target_bars: int) -> str:
    """Truncate ABC voice content to exactly target_bars measures."""
    bars_found = 0
    result_parts: list[str] = []
    for line in abc_text.strip().split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            result_parts.append(line)
            continue
        bar_positions = [m.start() for m in _BAR_RE.finditer(line)]
        if not bar_positions:
            result_parts.append(line)
            continue
        new_bars = bars_found + len(bar_positions)
        if new_bars <= target_bars:
            result_parts.append(line)
            bars_found = new_bars
        else:
            remaining = target_bars - bars_found
            if remaining > 0 and bar_positions:
                end_pos = bar_positions[remaining - 1] + 1
                result_parts.append(line[:end_pos])
                bars_found = target_bars
            break
    return "\n".join(result_parts)


def truncate_score_per_voice(abc_text: str, target_bars: int) -> str:
    """Truncate each voice independently to target_bars measures.

    Unlike truncate_to_bars which linearly cuts across all lines,
    this method parses voice blocks (V:1, V:2, ...) and truncates
    each one independently, preserving the multi-voice structure.
    """
    lines = abc_text.strip().split("\n")
    header_lines: list[str] = []
    voice_blocks: dict[str, list[str]] = {}
    current_voice: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            if current_voice is not None:
                voice_blocks.setdefault(current_voice, []).append(line)
            else:
                header_lines.append(line)
            continue

        # Detect voice directive (same regex as parse_voice_blocks)
        voice_match = re.match(r'^(V:\d[\+\d]*)', stripped)
        if voice_match:
            current_voice = voice_match.group(1)
            voice_blocks.setdefault(current_voice, []).append(line)
            continue

        # Header lines (before any V: directive)
        if current_voice is None:
            header_lines.append(line)
        else:
            voice_blocks.setdefault(current_voice, []).append(line)

    # Truncate each voice block independently
    truncated_blocks: dict[str, list[str]] = {}
    for voice_label, voice_lines in voice_blocks.items():
        truncated_blocks[voice_label] = truncate_voice_lines(
            voice_lines, target_bars
        )

    # Reassemble: header + each voice block
    result_parts = list(header_lines)
    for voice_label, voice_lines in truncated_blocks.items():
        result_parts.extend(voice_lines)

    return "\n".join(result_parts)


def truncate_voice_lines(lines: list[str], target_bars: int) -> list[str]:
    """Truncate a single voice's lines to target_bars measures."""
    bars_found = 0
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%") or stripped.startswith("V:"):
            result.append(line)
            continue
        bar_positions = [m.start() for m in _BAR_RE.finditer(line)]
        if not bar_positions:
            result.append(line)
            continue
        new_bars = bars_found + len(bar_positions)
        if new_bars <= target_bars:
            result.append(line)
            bars_found = new_bars
        else:
            remaining = target_bars - bars_found
            if remaining > 0 and bar_positions:
                end_pos = bar_positions[remaining - 1] + 1
                result.append(line[:end_pos])
            break
    return result


def store_fragment(
    fragments: dict[str, str],
    abc_parts: list[str],
    voice_label: str,
    abc_text: str,
    round_num: int = 0,
) -> None:
    """Store ABC text into fragments, splitting multi-voice rhythm output (V:3+V:4)."""
    # Stamp agent metadata
    agent = VOICE_TO_AGENT.get(voice_label, "unknown")
    abc_text = stamp_agent_meta(abc_text, agent, voice_label, round_num)

    if "+" in voice_label:
        rhythm_blocks = parse_voice_blocks(abc_text)
        if rhythm_blocks:
            for sub_label in rhythm_blocks:
                fragments[sub_label] = rhythm_blocks[sub_label]
            if abc_parts is not None:
                abc_parts.extend(f"{label}\n{content}" for label, content in rhythm_blocks.items())
            return
        logger.warning("Rhythmist output had no V:3/V:4 labels, storing as %s", voice_label)
    fragments[voice_label] = abc_text
    if abc_parts is not None:
        abc_parts.append(f"{voice_label}\n{abc_text}")


def inject_sf2_data(plan: dict, sf2_path: str, session_id: str = "") -> dict:
    """Inject SF2 profile data into plan's orchestration voices.

    Loads the SF2 profile, matches each voice's midi_program to the profile,
    and overrides range/register with real SF2 data.

    Returns a new plan dict with SF2 data injected (does not mutate input).
    """
    if not sf2_path:
        return plan

    from clef_server.sf2_profile import load_sf2_profile, midi_to_note

    profile = load_sf2_profile(sf2_path)
    if not profile:
        return plan

    presets = profile.get("presets", {})
    orch = plan.get("orchestration", {})
    new_orch = {}
    for role in ["melody", "harmony", "bass"]:
        part = dict(orch.get(role, {}))
        gm_program = part.get("midi_program")
        if isinstance(gm_program, int) and str(gm_program) in presets:
            preset_data = presets[str(gm_program)]
            part["sf2"] = preset_data
            # Override range/register with real SF2 data
            kr = preset_data.get("key_range", [0, 127])
            part["range"] = f"{midi_to_note(kr[0])}-{midi_to_note(kr[1])}"
            ss = preset_data.get("sweet_spot", [kr[0], kr[1]])
            part["register"] = f"{midi_to_note(ss[0])}-{midi_to_note(ss[1])}"
        new_orch[role] = part

    new_plan = {**plan, "orchestration": new_orch}

    logger.info(
        "Session %s: SF2 profile injected (%s, %d presets)",
        session_id, profile.get("sf2_name", "?"),
        profile.get("preset_count", 0),
    )
    return new_plan
