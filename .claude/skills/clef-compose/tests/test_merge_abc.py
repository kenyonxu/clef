"""Tests for merge_abc.py — ABC score merger with measure alignment."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from merge_abc import count_measures, pad_with_rests, merge


class TestCountMeasures:
    def test_simple_bars(self):
        content = "| d2 f2 a2 f2 | g2 b2 d'2 b2 |"
        assert count_measures(content) == 3

    def test_with_repeat_markers(self):
        content = "|: d2 f2 | g2 b2 :|"
        assert count_measures(content) == 2

    def test_double_bar_excluded(self):
        content = "| d2 f2 | g2 b2 ||"
        assert count_measures(content) == 2

    def test_empty_content(self):
        assert count_measures("") == 0

    def test_no_bars(self):
        assert count_measures("d2 f2 a2") == 0

    def test_mixed_bar_types(self):
        content = "|: d2 f2 | g2 b2 | a2 c2 :| d2 e2 ||"
        # |: counts, 2 standalone | count, :| and || excluded = 3
        assert count_measures(content) == 3


class TestPadWithRests:
    def test_pad_to_four(self):
        content = "| d2 f2 |"
        result = pad_with_rests(content, target_measures=4)
        assert count_measures(result) == 4

    def test_no_pad_needed(self):
        content = "| d2 f2 | g2 b2 |"
        result = pad_with_rests(content, target_measures=3)
        assert count_measures(result) == 3

    def test_pad_in_3_4(self):
        content = "| d2 f2 |"
        result = pad_with_rests(content, target_measures=3, time_signature="3/4")
        assert count_measures(result) == 3

    def test_pad_empty_content(self):
        result = pad_with_rests("", target_measures=2)
        assert count_measures(result) == 2

    def test_rests_contain_z(self):
        content = "| d2 f2 |"
        result = pad_with_rests(content, target_measures=3)
        assert "z" in result


class TestGenerateHeader:
    def _plan(self, **overrides):
        base = {"title": "Test", "time_signature": "4/4", "bpm": 120, "key": "D"}
        base.update(overrides)
        return base

    def test_basic_header(self):
        from merge_abc import generate_header
        result = generate_header(self._plan())
        assert "%%abc-version 2.1" in result
        assert "X:1" in result
        assert "T:Test" in result
        assert "M:4/4" in result
        assert "L:1/8" in result
        assert "Q:1/4=120" in result
        assert "K:D" in result

    def test_minor_key(self):
        from merge_abc import generate_header
        result = generate_header(self._plan(key="Am"))
        assert "K:Am" in result


class TestMerge:
    def _plan(self, **overrides):
        base = {
            "title": "Test",
            "time_signature": "4/4",
            "bpm": 120,
            "key": "D",
            "orchestration": {
                "melody": {"channel": 0, "instrument": 73, "name": "Flute"},
                "harmony": {"channel": 1, "instrument": 48, "name": "Strings"},
            }
        }
        for k, v in overrides.items():
            if k == "orchestration":
                base[k].update(v)
            else:
                base[k] = v
        return base

    def test_merge_full(self):
        plan = self._plan()
        fragments = {
            "V:1": '| d2 f2 | g2 b2 |',
            "V:2": '| [FAc]2 [FAc]2 | [GBd]2 [GBd]2 |',
        }
        result = merge(plan, fragments, mode='full')
        assert 'K:D' in result
        assert 'V:1' in result
        assert 'V:2' in result

    def test_merge_solo(self):
        plan = self._plan()
        fragments = {"V:1": '| d2 f2 a2 f2 |'}
        result = merge(plan, fragments, mode='solo')
        assert 'V:1' in result
        assert 'V:2' not in result

    def test_measure_alignment(self):
        from merge_abc import pad_with_rests
        # V:1 has 4 bars, V:2 has 2 bars
        v1 = '| d2 f2 | g2 b2 | a2 c2 |'
        v2 = '| [FAc]2 [FAc]2 |'
        assert count_measures(v1) == 4
        assert count_measures(v2) == 2
        # After padding V:2 to match V:1, it should have 4 bars
        padded_v2 = pad_with_rests(v2, target_measures=4)
        assert count_measures(padded_v2) == 4

    def test_midi_directives(self):
        plan = self._plan()
        fragments = {"V:1": '| d2 f2 |'}
        result = merge(plan, fragments, mode='full')
        assert '%%MIDI program 73' in result

    def test_merge_returns_string(self):
        plan = self._plan()
        fragments = {"V:1": '| d2 f2 |'}
        result = merge(plan, fragments, mode='full')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_semantic_voice_mapping_with_reversed_keys(self):
        """Orchestration keys in non-standard order should still map correctly by role name."""
        plan = {
            "title": "Test",
            "time_signature": "4/4",
            "bpm": 120,
            "key": "D",
            "orchestration": {
                "drums": {"channel": 9, "instrument": 0, "name": "Drums"},
                "bass": {"channel": 2, "instrument": 32, "name": "Bass"},
                "harmony": {"channel": 1, "instrument": 48, "name": "Strings"},
                "melody": {"channel": 0, "instrument": 73, "name": "Flute"},
            }
        }
        fragments = {
            "V:1": '| d2 f2 |',
            "V:2": '| [FAc]2 [FAc]2 |',
        }
        result = merge(plan, fragments, mode='full')
        # V:1 should get melody (channel 0, program 73) regardless of dict order
        assert '%%MIDI channel 0' in result
        assert '%%MIDI program 73' in result
        # V:2 should get harmony (channel 1, program 48)
        assert '%%MIDI channel 1' in result
        assert '%%MIDI program 48' in result

    def test_semantic_voice_mapping_all_four_voices(self):
        """All 4 standard voices should map to correct channels by semantic role."""
        plan = {
            "title": "Test",
            "time_signature": "4/4",
            "bpm": 120,
            "key": "C",
            "orchestration": {
                "melody": {"channel": 0, "instrument": 73},
                "harmony": {"channel": 1, "instrument": 48},
                "bass": {"channel": 2, "instrument": 32},
                "drums": {"channel": 9, "instrument": 0},
            }
        }
        fragments = {
            "V:1": '| c2 e2 |',
            "V:2": '| [CEG]2 [CEG]2 |',
            "V:3": '| C,2 C,2 |',
            "V:4": '| z2 z2 |',
        }
        result = merge(plan, fragments, mode='full')

        # V:1 -> melody channel 0
        lines = result.split('\n')
        v1_idx = next(i for i, l in enumerate(lines) if 'V:1' in l)
        assert '%%MIDI channel 0' in lines[v1_idx - 2]
        assert '%%MIDI program 73' in lines[v1_idx - 1]

        # V:2 -> harmony channel 1
        v2_idx = next(i for i, l in enumerate(lines) if 'V:2' in l)
        assert '%%MIDI channel 1' in lines[v2_idx - 2]
        assert '%%MIDI program 48' in lines[v2_idx - 1]

        # V:3 -> bass channel 2
        v3_idx = next(i for i, l in enumerate(lines) if 'V:3' in l)
        assert '%%MIDI channel 2' in lines[v3_idx - 2]
        assert '%%MIDI program 32' in lines[v3_idx - 1]

        # V:4 -> drums channel 9
        v4_idx = next(i for i, l in enumerate(lines) if 'V:4' in l)
        assert '%%MIDI channel 9' in lines[v4_idx - 2]

    def test_semantic_mapping_fallback_to_positional(self):
        """Non-standard role names should fall back to positional indexing."""
        plan = {
            "title": "Test",
            "time_signature": "4/4",
            "bpm": 120,
            "key": "C",
            "orchestration": {
                "lead": {"channel": 3, "instrument": 80},
                "pad": {"channel": 4, "instrument": 90},
            }
        }
        fragments = {
            "V:1": '| c2 e2 |',
            "V:2": '| [CEG]2 [CEG]2 |',
        }
        result = merge(plan, fragments, mode='full')
        # "lead" and "pad" are not in the voice_to_role map,
        # so fallback to positional: V:1 -> index 0 -> lead
        assert '%%MIDI channel 3' in result
        assert '%%MIDI channel 4' in result
