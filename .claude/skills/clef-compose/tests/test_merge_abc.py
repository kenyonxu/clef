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
