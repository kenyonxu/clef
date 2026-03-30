"""ABC score merger — combines multiple voice fragments into a single score.abc.

Handles measure alignment via bar-line counting and rest padding,
generates proper ABC headers from plan.json metadata, and produces
voice blocks with %%MIDI directives.
"""

import re


def count_measures(content: str) -> int:
    """Count bar lines (``|``) excluding double bars (``||``) and repeat-end (``:|``).

    Repeat-start (``|:``) counts as a bar line because it marks a measure boundary.
    Repeat-end (``:|``) and double bar (``||``) are excluded as they are
    structural markers, not measure-count boundaries.
    """
    if not content:
        return 0

    # Remove double bars and repeat-end markers, then count remaining |
    cleaned = re.sub(r'\|\|', '', content)
    cleaned = re.sub(r':\|', '', cleaned)
    return cleaned.count('|')


def _parse_time_signature(time_signature: str) -> tuple[int, int]:
    """Parse '4/4' into (4, 4)."""
    parts = time_signature.split('/')
    return (int(parts[0]), int(parts[1]))


def _rest_duration_for_measure(time_signature: str) -> str:
    """Return ABC rest notation for a full measure.

    In ABC with L:1/8 (eighth-note unit), a quarter note is ``2``.
    So a 4/4 measure = 4 quarter notes = 4 * 2 = 8 eighth-note units = ``z8``.
    A 3/4 measure = 3 quarter notes = 3 * 2 = 6 eighth-note units = ``z6``.
    """
    beats_per_measure, beat_unit = _parse_time_signature(time_signature)
    # L:1/8 means each unit is an eighth note.
    # One beat (quarter note) = 2 eighth-note units.
    # Total eighth-note units per measure = beats * (beat_unit_denominator / unit_denominator)
    # But since beat_unit is always 4 and L is always 1/8:
    # eighth_units = beats_per_measure * (4 / 8) * 8 = beats_per_measure * 4
    # Wait, let me think more carefully.
    #
    # L:1/8 means the default note length is 1/8.
    # A quarter note is written as "2" (because 2 * 1/8 = 1/4).
    # A measure of 4/4 has 4 quarter notes = 4 * 2 = 8 in ABC duration units.
    # A measure of 3/4 has 3 quarter notes = 3 * 2 = 6 in ABC duration units.
    # General: beats_per_measure * (4 / 8) * 8 = beats_per_measure * 4
    # Simpler: beats_per_measure * (1 / (1/8) * (1/4)) = beats_per_measure * 2
    eighth_units = beats_per_measure * 2
    return f"z{eighth_units}"


def pad_with_rests(content: str, target_measures: int, time_signature: str = "4/4") -> str:
    """Pad a voice fragment with rest measures to reach *target_measures*.

    If the content already has >= target_measures, returns it unchanged.
    """
    current = count_measures(content)
    if current >= target_measures:
        return content

    deficit = target_measures - current
    rest_note = _rest_duration_for_measure(time_signature)
    rest_measures = " ".join([f"| {rest_note}"] * deficit)
    return f"{content} {rest_measures}"


def generate_header(plan: dict) -> str:
    """Generate ABC file header from plan.json fields."""
    title = plan.get("title", "Untitled")
    time_signature = plan.get("time_signature", "4/4")
    bpm = plan.get("bpm", 120)
    key = plan.get("key", "C")

    # Key should be just the note name (e.g. "D", "Am"), not "D major"
    # We trust the plan to provide it correctly.

    lines = [
        "%%abc-version 2.1",
        "X:1",
        f"T:{title}",
        f"M:{time_signature}",
        "L:1/8",
        f"Q:1/4={bpm}",
        f"K:{key}",
    ]
    return "\n".join(lines)


def merge(plan: dict, fragments: dict, mode: str = "full") -> str:
    """Merge multiple voice fragments into a complete ABC score.

    Args:
        plan: Composition plan dict with title, key, bpm, time_signature, orchestration.
        fragments: Dict mapping voice labels (e.g. ``"V:1"``) to ABC content strings.
        mode: ``'full'`` includes all voices, ``'solo'`` includes only V:1.

    Returns:
        Complete ABC string ready to write to score.abc.
    """
    time_signature = plan.get("time_signature", "4/4")
    orchestration = plan.get("orchestration", {})

    # Determine which voices to include
    voice_labels = sorted(fragments.keys())
    if mode == "solo":
        voice_labels = [v for v in voice_labels if v == "V:1"]
        if not voice_labels:
            # Fallback: use first available voice
            voice_labels = [sorted(fragments.keys())[0]]

    # Count measures per voice to find max
    measure_counts = {v: count_measures(fragments[v]) for v in voice_labels}
    max_measures = max(measure_counts.values()) if measure_counts else 0

    # Pad all voices to max measures
    padded = {}
    for v in voice_labels:
        padded[v] = pad_with_rests(fragments[v], max_measures, time_signature)

    # Build output
    parts = [generate_header(plan)]

    for v in voice_labels:
        content = padded[v]
        # Look up MIDI directives from orchestration
        voice_num = v.replace("V:", "")
        midi_lines = []

        # Map voice number to orchestration role by semantic key name
        voice_to_role = {"1": "melody", "2": "harmony", "3": "bass", "4": "drums"}
        role = voice_to_role.get(voice_num) if voice_num.isdigit() else None

        if role and role in orchestration:
            orch = orchestration[role]
            channel = orch.get("channel", 0)
            instrument = orch.get("instrument", 0)
            midi_lines.append(f"%%MIDI channel {channel}")
            midi_lines.append(f"%%MIDI program {instrument}")
        elif voice_num.isdigit():
            # Fallback: try positional indexing for non-standard roles
            orch_keys = list(orchestration.keys())
            voice_index = int(voice_num) - 1
            if 0 <= voice_index < len(orch_keys):
                orch = orchestration[orch_keys[voice_index]]
                channel = orch.get("channel", voice_index)
                instrument = orch.get("instrument", 0)
                midi_lines.append(f"%%MIDI channel {channel}")
                midi_lines.append(f"%%MIDI program {instrument}")

        parts.extend(midi_lines)
        parts.append(v)
        parts.append(content)

    return "\n".join(parts)
