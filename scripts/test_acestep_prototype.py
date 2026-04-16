"""Tests for ACE-Step prototype plan-to-parameter mapping."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from acestep_prototype import build_acestep_params


def _sample_plan():
    """Return a sample clef plan.json for testing."""
    return {
        "title": "Village Morning",
        "key": "G",
        "scale": "major",
        "bpm": 120,
        "time_signature": "4/4",
        "total_bars": 16,
        "form": "AB",
        "sections": [
            {"id": "A", "name": "Intro", "measures": 4, "energy_level": 3, "dynamics": "mp"},
            {"id": "B", "name": "Verse", "measures": 8, "energy_level": 5, "dynamics": "mf"},
            {"id": "C", "name": "Outro", "measures": 4, "energy_level": 2, "dynamics": "p"},
        ],
        "orchestration": {
            "melody": {"name": "Violin", "channel": 0, "instrument": 40},
            "harmony": {"name": "Nylon Guitar", "channel": 1, "instrument": 24},
            "bass": {"name": "Acoustic Bass", "channel": 2, "instrument": 32},
            "drums": {"name": "Drums", "channel": 9, "instrument": 0},
        },
        "style": "田园晨曲",
        "mood": "温暖平和",
    }


def test_text2music_basic_mapping():
    plan = _sample_plan()
    params = build_acestep_params(plan, "text2music", None)

    assert params["task_type"] == "text2music"
    assert params["bpm"] == 120
    assert params["key_scale"] == "G Major"
    assert params["time_signature"] == "4"
    assert params["audio_duration"] == 32.0  # 16 bars * 4 beats * 60 / 120 bpm = 32s
    assert params["thinking"] is True
    assert "田园晨曲" in params["prompt"]


def test_text2music_duration_from_sections():
    plan = _sample_plan()
    del plan["total_bars"]
    params = build_acestep_params(plan, "text2music", None)
    assert params["audio_duration"] == 32.0  # 16 bars * 4 beats * 60 / 120 bpm = 32s


def test_text2music_minor_key():
    plan = _sample_plan()
    plan["key"] = "A"
    plan["scale"] = "minor"
    params = build_acestep_params(plan, "text2music", None)
    assert params["key_scale"] == "A minor"


def test_cover_mode_with_reference():
    plan = _sample_plan()
    params = build_acestep_params(plan, "cover", "/tmp/reference.wav")
    assert params["task_type"] == "cover"
    assert params["src_audio_path"] == "/tmp/reference.wav"


def test_time_signature_parsing():
    plan = _sample_plan()

    plan["time_signature"] = "3/4"
    assert build_acestep_params(plan, "text2music", None)["time_signature"] == "3"

    plan["time_signature"] = "6/8"
    assert build_acestep_params(plan, "text2music", None)["time_signature"] == "6"

    plan["time_signature"] = "2/4"
    assert build_acestep_params(plan, "text2music", None)["time_signature"] == "2"


def test_instrument_prompt_includes_orchestration():
    plan = _sample_plan()
    params = build_acestep_params(plan, "text2music", None)
    assert "violin" in params["prompt"].lower()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
