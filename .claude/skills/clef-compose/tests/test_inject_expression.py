"""Tests for inject_expression.py - expression plan injection into MIDI files."""

import sys
import os
import io
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import mido
from inject_expression import inject, _convert_sections_format


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')


def _make_base_midi(channel: int = 0, ticks_per_beat: int = 480) -> str:
	"""Create a minimal base MIDI file and return its temp path."""
	mid = mido.MidiFile()
	mid.ticks_per_beat = ticks_per_beat

	# Tempo track
	tempo_track = mido.MidiTrack()
	tempo_track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
	mid.tracks.append(tempo_track)

	# Melody track with a few notes
	track = mido.MidiTrack()
	track.append(mido.Message('program_change', program=73, channel=channel, time=0))
	track.append(mido.Message('note_on', note=60, velocity=100, channel=channel, time=0))
	track.append(mido.Message('note_off', note=60, velocity=100, channel=channel, time=480))
	track.append(mido.Message('note_on', note=64, velocity=100, channel=channel, time=0))
	track.append(mido.Message('note_off', note=64, velocity=100, channel=channel, time=480))
	mid.tracks.append(track)

	path = tempfile.mktemp(suffix='.mid')
	mid.save(path)
	return path


def test_inject_cc():
	"""CC7 (volume) events from the expression plan should appear in output."""
	base_path = _make_base_midi()
	output_path = tempfile.mktemp(suffix='.mid')
	plan_path = os.path.join(FIXTURES_DIR, 'expression_plan.json')

	inject(base_path, plan_path, output_path)

	result = mido.MidiFile(output_path)
	cc_events = [
		m for t in result.tracks
		for m in t
		if m.type == 'control_change' and m.control == 7
	]
	assert len(cc_events) == 2, f"Expected 2 CC7 events, got {len(cc_events)}"
	assert cc_events[0].value == 90
	assert cc_events[1].value == 70

	os.unlink(base_path)
	os.unlink(output_path)


def test_inject_pitch_bend():
	"""Pitch bend events from the expression plan should appear in output."""
	base_path = _make_base_midi()
	output_path = tempfile.mktemp(suffix='.mid')
	plan_path = os.path.join(FIXTURES_DIR, 'expression_plan.json')

	inject(base_path, plan_path, output_path)

	result = mido.MidiFile(output_path)
	pb_events = [
		m for t in result.tracks
		for m in t
		if m.type == 'pitchwheel'
	]
	assert len(pb_events) == 2, f"Expected 2 pitch_bend events, got {len(pb_events)}"
	# Plan uses unsigned 0-16383; mido stores signed -8192..8191
	# 12288 unsigned -> 4096 signed, 8192 unsigned -> 0 signed (center)
	assert pb_events[0].pitch == 4096
	assert pb_events[1].pitch == 0

	os.unlink(base_path)
	os.unlink(output_path)


def test_preserves_existing_notes():
	"""Existing note_on/note_off events must not be modified."""
	base_path = _make_base_midi()
	output_path = tempfile.mktemp(suffix='.mid')
	plan_path = os.path.join(FIXTURES_DIR, 'expression_plan.json')

	inject(base_path, plan_path, output_path)

	result = mido.MidiFile(output_path)
	# Melody track is track index 1
	melody_track = result.tracks[1]
	note_ons = [m for m in melody_track if m.type == 'note_on']
	note_offs = [m for m in melody_track if m.type == 'note_off']
	assert len(note_ons) == 2, f"Expected 2 note_on, got {len(note_ons)}"
	assert len(note_offs) == 2, f"Expected 2 note_off, got {len(note_offs)}"

	# Verify note values are unchanged
	assert note_ons[0].note == 60
	assert note_ons[1].note == 64

	os.unlink(base_path)
	os.unlink(output_path)


def test_inject_at_correct_absolute_ticks():
	"""Events should be placed at the correct absolute tick positions."""
	base_path = _make_base_midi(ticks_per_beat=480)
	output_path = tempfile.mktemp(suffix='.mid')
	plan_path = os.path.join(FIXTURES_DIR, 'expression_plan.json')

	inject(base_path, plan_path, output_path)

	result = mido.MidiFile(output_path)
	melody_track = result.tracks[1]

	# Convert to absolute time
	abs_time = 0
	for msg in melody_track:
		abs_time += msg.time

	# Verify CC7 at beat 0 (tick 0) has value 90
	cc_at_0 = [
		m for m in melody_track
		if m.type == 'control_change' and m.control == 7 and m.value == 90
	]
	assert len(cc_at_0) == 1

	# The CC at beat 2 (tick 960) should have value 70
	abs_time = 0
	cc_70_found = False
	for msg in melody_track:
		abs_time += msg.time
		if msg.type == 'control_change' and msg.control == 7 and msg.value == 70:
			assert abs_time == 960, f"CC70 at tick {abs_time}, expected 960"
			cc_70_found = True
	assert cc_70_found, "CC7 value=70 not found"

	os.unlink(base_path)
	os.unlink(output_path)


def test_no_matching_channel():
	"""If plan targets a channel not in the MIDI, the track should be skipped gracefully."""
	base_path = _make_base_midi(channel=0)
	output_path = tempfile.mktemp(suffix='.mid')

	# Plan targeting channel 9 (not in base MIDI)
	plan = {"tracks": [{"channel": 9, "events": [
		{"time_beats": 0.0, "type": "cc", "control": 7, "value": 90}
	]}]}
	plan_path = tempfile.mktemp(suffix='.json')
	with open(plan_path, 'w') as f:
		import json
		json.dump(plan, f)

	inject(base_path, plan_path, output_path)

	# Should succeed without error, and no CC events on channel 9
	result = mido.MidiFile(output_path)
	cc_events = [m for t in result.tracks for m in t if m.type == 'control_change']
	assert len(cc_events) == 0

	os.unlink(base_path)
	os.unlink(output_path)
	os.unlink(plan_path)


def test_preserves_tempo_track():
	"""Tempo track (track 0) should remain untouched."""
	base_path = _make_base_midi()
	output_path = tempfile.mktemp(suffix='.mid')
	plan_path = os.path.join(FIXTURES_DIR, 'expression_plan.json')

	inject(base_path, plan_path, output_path)

	result = mido.MidiFile(output_path)
	tempo_track = result.tracks[0]
	# Should still have exactly the set_tempo meta message
	tempo_msgs = [m for m in tempo_track if m.type == 'set_tempo']
	assert len(tempo_msgs) == 1
	assert tempo_msgs[0].tempo == 500000  # 120 BPM

	os.unlink(base_path)
	os.unlink(output_path)


# ── Sections format conversion tests ──────────────────────────────────────


def test_sections_format_converts_cc7_to_tracks():
	"""Sections format with cc7 shorthand should convert to tracks format."""
	plan = {
		"sections": [
			{"id": "A", "channels": {"0": {"cc7": 90}}},
			{"id": "B", "channels": {"0": {"cc7": 110}}},
		]
	}
	plan_path = tempfile.mktemp(suffix='.json')
	with open(plan_path, 'w') as f:
		json.dump(plan, f)

	result = _convert_sections_format(plan, plan_path)
	assert len(result) == 1
	assert result[0]['channel'] == 0
	events = result[0]['events']
	assert len(events) == 2
	# Section A at beat 0 (default when no plan.json)
	assert events[0]['type'] == 'cc'
	assert events[0]['control'] == 7
	assert events[0]['value'] == 90
	assert events[0]['time_beats'] == 0
	# Section B at beat 0 (default when no plan.json)
	assert events[1]['value'] == 110

	os.unlink(plan_path)


def test_sections_format_with_plan_json_beat_ranges():
	"""Sections format should use plan.json for correct beat offsets."""
	plan_dir = tempfile.mkdtemp()
	# Create a companion plan.json with section beat ranges
	companion_plan = {
		"sections": [
			{"id": "A", "measures": 8, "start_beat": 0},
			{"id": "B", "measures": 8, "start_beat": 32},
			{"id": "A2", "measures": 8, "start_beat": 64},
		],
		"time_signature": "4/4",
	}
	companion_path = os.path.join(plan_dir, 'plan.json')
	with open(companion_path, 'w') as f:
		json.dump(companion_plan, f)

	plan = {
		"sections": [
			{"id": "A", "channels": {"0": {"cc7": 85}}},
			{"id": "B", "channels": {"0": {"cc7": 110}}},
			{"id": "A2", "channels": {"0": {"cc7": 90}}},
		]
	}
	plan_path = os.path.join(plan_dir, 'expression_plan.json')
	with open(plan_path, 'w') as f:
		json.dump(plan, f)

	result = _convert_sections_format(plan, plan_path)
	assert len(result) == 1
	events = result[0]['events']
	assert events[0]['time_beats'] == 0, f"A section at {events[0]['time_beats']}"
	assert events[1]['time_beats'] == 32, f"B section at {events[1]['time_beats']}"
	assert events[2]['time_beats'] == 64, f"A2 section at {events[2]['time_beats']}"

	os.unlink(plan_path)
	os.unlink(companion_path)
	os.rmdir(plan_dir)


def test_sections_format_multiple_channels():
	"""Sections format with multiple channels should produce separate tracks."""
	plan = {
		"sections": [
			{
				"id": "A",
				"channels": {
					"0": {"cc7": 100, "cc11": 80},
					"1": {"cc7": 75, "cc91": 60},
				}
			}
		]
	}
	plan_path = tempfile.mktemp(suffix='.json')
	with open(plan_path, 'w') as f:
		json.dump(plan, f)

	result = _convert_sections_format(plan, plan_path)
	assert len(result) == 2

	channels = {t['channel'] for t in result}
	assert 0 in channels
	assert 1 in channels

	ch0_events = next(t['events'] for t in result if t['channel'] == 0)
	ch1_events = next(t['events'] for t in result if t['channel'] == 1)

	# Channel 0: cc7=100, cc11=80
	assert any(e['control'] == 7 and e['value'] == 100 for e in ch0_events)
	assert any(e['control'] == 11 and e['value'] == 80 for e in ch0_events)

	# Channel 1: cc7=75, cc91=60
	assert any(e['control'] == 7 and e['value'] == 75 for e in ch1_events)
	assert any(e['control'] == 91 and e['value'] == 60 for e in ch1_events)

	os.unlink(plan_path)


def test_sections_format_pitch_bend():
	"""Sections format with pitch_bend should convert correctly."""
	plan = {
		"sections": [
			{
				"id": "A",
				"channels": {
					"0": {
						"cc7": 100,
						"pitch_bend": [
							{"offset_beats": 7.75, "value": 12288},
							{"offset_beats": 8.25, "value": 8192},
						]
					}
				}
			}
		]
	}
	plan_path = tempfile.mktemp(suffix='.json')
	with open(plan_path, 'w') as f:
		json.dump(plan, f)

	result = _convert_sections_format(plan, plan_path)
	assert len(result) == 1
	events = result[0]['events']

	pb_events = [e for e in events if e['type'] == 'pitch_bend']
	assert len(pb_events) == 2
	assert pb_events[0]['value'] == 12288
	assert pb_events[0]['time_beats'] == 7.75
	assert pb_events[1]['value'] == 8192
	assert pb_events[1]['time_beats'] == 8.25

	os.unlink(plan_path)


def test_sections_format_empty_sections():
	"""Sections format with no events should return empty list."""
	plan = {"sections": [{"id": "A", "channels": {}}]}
	plan_path = tempfile.mktemp(suffix='.json')
	with open(plan_path, 'w') as f:
		json.dump(plan, f)

	result = _convert_sections_format(plan, plan_path)
	assert result == []

	os.unlink(plan_path)


def test_inject_sections_format_end_to_end():
	"""Full inject() with sections format should produce CC events in output MIDI."""
	base_path = _make_base_midi(channel=0)
	output_path = tempfile.mktemp(suffix='.mid')

	plan = {
		"sections": [
			{"id": "A", "channels": {"0": {"cc7": 95, "cc11": 80}}},
			{"id": "B", "channels": {"0": {"cc7": 115}}},
		]
	}
	plan_path = tempfile.mktemp(suffix='.json')
	with open(plan_path, 'w') as f:
		json.dump(plan, f)

	inject(base_path, plan_path, output_path)

	result = mido.MidiFile(output_path)
	melody_track = result.tracks[1]
	cc_events = [m for m in melody_track if m.type == 'control_change']
	# cc7=95, cc11=80, cc7=115 -> 3 events
	assert len(cc_events) == 3, f"Expected 3 CC events, got {len(cc_events)}"

	cc7_values = [m.value for m in cc_events if m.control == 7]
	assert 95 in cc7_values
	assert 115 in cc7_values

	cc11_values = [m.value for m in cc_events if m.control == 11]
	assert 80 in cc11_values

	os.unlink(base_path)
	os.unlink(output_path)
	os.unlink(plan_path)


def test_inject_unknown_format_prints_error():
	"""inject() with unrecognized format should print error to stderr."""
	base_path = _make_base_midi()
	output_path = tempfile.mktemp(suffix='.mid')

	plan = {"sections": [{"id": "A"}], "tracks": [], "bogus_key": True}
	# Remove sections and tracks to trigger unknown format
	del plan["sections"]
	del plan["tracks"]

	plan_path = tempfile.mktemp(suffix='.json')
	with open(plan_path, 'w') as f:
		json.dump(plan, f)

	# Capture stderr
	old_stderr = sys.stderr
	sys.stderr = io.StringIO()

	inject(base_path, plan_path, output_path)

	stderr_output = sys.stderr.getvalue()
	sys.stderr = old_stderr

	assert "unrecognized format" in stderr_output, f"Expected error message, got: {stderr_output}"
	# No CC events should be injected
	result = mido.MidiFile(output_path)
	cc_events = [m for t in result.tracks for m in t if m.type == 'control_change']
	assert len(cc_events) == 0

	os.unlink(base_path)
	os.unlink(output_path)
	os.unlink(plan_path)


if __name__ == '__main__':
	test_inject_cc()
	test_inject_pitch_bend()
	test_preserves_existing_notes()
	test_inject_at_correct_absolute_ticks()
	test_no_matching_channel()
	test_preserves_tempo_track()
	test_sections_format_converts_cc7_to_tracks()
	test_sections_format_with_plan_json_beat_ranges()
	test_sections_format_multiple_channels()
	test_sections_format_pitch_bend()
	test_sections_format_empty_sections()
	test_inject_sections_format_end_to_end()
	test_inject_unknown_format_prints_error()
	print("All tests passed!")
