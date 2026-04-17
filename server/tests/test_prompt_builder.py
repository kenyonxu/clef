"""Tests for clef_server.prompt_builder."""

from clef_server.prompt_builder import build_create_message, build_plan_summary


class TestBuildPlanSummary:
    """Tests for build_plan_summary."""

    def test_includes_key_fields(self):
        plan = {
            "total_bars": 16,
            "bpm": 120,
            "time_signature": "4/4",
            "key": "C",
            "form": "ABA",
            "sections": [
                {"name": "A", "measures": 4},
                {"name": "B", "measures": 8},
                {"name": "A'", "measures": 4},
            ],
            "orchestration": {
                "melody": {"name": "Piano", "instrument": "Piano"},
                "harmony": {"name": "Strings", "instrument": "Strings"},
            },
            "demo_length_bars": 4,
        }
        result = build_plan_summary(plan)

        assert "duration" in result
        assert "section_structure" in result
        assert "orchestration_desc" in result
        assert "sf2_status" in result
        assert "demo_length" in result

        # Verify duration computation: 16 bars * 4 beats / 120 bpm * 60 = 32 sec
        assert result["duration"] == "~32秒"
        assert result["section_structure"] == "ABA（4+8+4 小节）"
        assert "Piano旋律" in result["orchestration_desc"]
        assert "Strings和声" in result["orchestration_desc"]
        assert result["sf2_status"] == "未配置"
        assert "4 小节" in result["demo_length"]

    def test_duration_over_60_seconds(self):
        plan = {
            "total_bars": 120,
            "bpm": 60,
            "time_signature": "4/4",
            "form": "ABC",
            "sections": [{"name": "A", "measures": 120}],
        }
        result = build_plan_summary(plan)
        # 120 * 4 / 60 * 60 = 480 sec = 8 min 0 sec
        assert result["duration"] == "~8分0秒"

    def test_handles_empty_plan(self):
        result = build_plan_summary({})
        assert result["duration"] == "~0秒"
        assert result["sf2_status"] == "未配置"
        assert result["orchestration_desc"] == ""
        assert result["demo_length"] == "0 小节"

    def test_sf2_status_with_loaded_soundfonts(self):
        plan = {
            "total_bars": 8,
            "bpm": 120,
            "time_signature": "4/4",
            "form": "AB",
            "sections": [{"name": "A", "measures": 4}, {"name": "B", "measures": 4}],
            "orchestration": {
                "melody": {"sf2": {"key_range": [36, 96]}},
                "harmony": {"sf2": {"key_range": [36, 96]}},
                "bass": {"sf2": {"key_range": [28, 72]}},
            },
        }
        result = build_plan_summary(plan)
        assert "3 个声部音色" in result["sf2_status"]

    def test_default_time_signature(self):
        result = build_plan_summary({"total_bars": 4, "bpm": 120})
        # Missing time_signature defaults to 4/4 → 4 beats
        assert result["duration"] == "~8秒"


class TestBuildCreateMessage:
    """Tests for build_create_message."""

    def test_returns_string(self):
        plan = {
            "total_bars": 8,
            "bpm": 120,
            "time_signature": "4/4",
            "key": "G",
            "scale": "minor",
            "form": "AB",
            "sections": [
                {"name": "A", "measures": 4, "energy_level": "low", "melody_strategy": "new"},
                {"name": "B", "measures": 4, "energy_level": "high", "melody_strategy": "climax"},
            ],
            "orchestration": {
                "melody": {"instrument": "Violin", "range": "G3-A6", "register": "G4-D6"},
            },
        }
        result = build_create_message("melody", plan)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_includes_section_structure_hints(self):
        plan = {
            "total_bars": 12,
            "bpm": 100,
            "time_signature": "3/4",
            "key": "C",
            "form": "ABA",
            "sections": [
                {"name": "Intro", "measures": 4, "energy_level": "low", "melody_strategy": "new"},
                {"name": "Bridge", "measures": 4, "energy_level": "mid", "melody_strategy": "development"},
                {"name": "Outro", "measures": 4, "energy_level": "low", "melody_strategy": "recap"},
            ],
            "orchestration": {},
        }
        result = build_create_message("melody", plan)

        assert "Sections" in result
        assert "Intro" in result
        assert "Bridge" in result
        assert "Outro" in result
        assert "EXACTLY 12 bar lines" in result

    def test_melody_rules_included(self):
        plan = {
            "total_bars": 8,
            "bpm": 120,
            "time_signature": "4/4",
            "sections": [],
            "orchestration": {"melody": {}},
        }
        result = build_create_message("melody", plan)
        assert "Melody Rules" in result
        assert "melody_strategy" in result

    def test_harmony_rules_included(self):
        plan = {
            "total_bars": 8,
            "bpm": 120,
            "time_signature": "4/4",
            "sections": [],
            "orchestration": {"harmony": {}},
        }
        result = build_create_message("harmony", plan)
        assert "Harmony Rules" in result
        assert "measure must be COMPLETELY filled" in result

    def test_bass_rules_included(self):
        plan = {
            "total_bars": 8,
            "bpm": 120,
            "time_signature": "4/4",
            "sections": [],
            "orchestration": {"bass": {}},
        }
        result = build_create_message("rhythm", plan)
        assert "Bass & Drum Rules" in result

    def test_voice_label_mapping(self):
        plan = {
            "total_bars": 4,
            "bpm": 120,
            "time_signature": "4/4",
            "sections": [],
            "orchestration": {},
        }
        result = build_create_message("melody", plan)
        assert "V:1" in result

        result = build_create_message("harmony", plan)
        assert "V:2" in result

        result = build_create_message("rhythm", plan)
        assert "V:3+V:4" in result

    def test_duration_reference_present(self):
        plan = {
            "total_bars": 8,
            "bpm": 120,
            "time_signature": "4/4",
            "sections": [],
            "orchestration": {},
        }
        result = build_create_message("melody", plan)
        assert "Duration Self-Check" in result
        assert "8 eighth-note units" in result
