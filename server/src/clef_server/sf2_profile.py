"""SF2 profile loader — parse SoundFont files and cache composer-friendly JSON.

Wraps the standalone sf2_profiler.py script via subprocess, with automatic
caching based on SF2 file modification time.
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PROFILER_SCRIPT = Path(__file__).resolve().parent.parent.parent.parent / \
    ".claude" / "skills" / "clef-compose" / "scripts" / "sf2_profiler.py"


def load_sf2_profile(sf2_path: str) -> dict | None:
    """Load or generate SF2 profile JSON for the given SF2 file.

    Returns the profile dict (with 'presets' keyed by GM program number as string),
    or None if the SF2 file doesn't exist or profiling fails.
    """
    sf2 = Path(sf2_path)
    if not sf2.exists():
        return None

    # Profile cached next to the SF2 file: GeneralUser-GS.sf2 → GeneralUser-GS.sf2.profile.json
    profile_path = sf2.with_name(sf2.stem + ".sf2.profile.json")

    # Regenerate if SF2 is newer than profile
    needs_regen = False
    if not profile_path.exists():
        needs_regen = True
    else:
        try:
            if sf2.stat().st_mtime > profile_path.stat().st_mtime:
                needs_regen = True
        except OSError:
            needs_regen = True

    if needs_regen:
        logger.info("Generating SF2 profile for %s", sf2.name)
        try:
            _run_profiler(str(sf2), str(profile_path))
        except Exception as e:
            logger.error("SF2 profiler failed: %s", e)
            if not profile_path.exists():
                return None
            # Return stale profile if available
            logger.warning("Using stale SF2 profile from %s", profile_path)

    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to read SF2 profile: %s", e)
        return None


def _run_profiler(sf2_path: str, output_path: str) -> None:
    """Run sf2_profiler.py via subprocess."""
    if not _PROFILER_SCRIPT.exists():
        raise RuntimeError(f"sf2_profiler.py not found at {_PROFILER_SCRIPT}")

    result = subprocess.run(
        [sys.executable, str(_PROFILER_SCRIPT), sf2_path, "-o", output_path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"sf2_profiler exited with {result.returncode}: {result.stderr}")


def midi_to_note(midi: int) -> str:
    """Convert MIDI note number to ABC note name (e.g. 60 → 'C4').

    Input is clamped to valid MIDI range 0-127.
    """
    midi = max(0, min(127, int(midi)))
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (midi // 12) - 1
    return f"{notes[midi % 12]}{octave}"
