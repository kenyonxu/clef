"""Inject expression plan events (CC, pitch bend) into a base MIDI file.

Reads an expression_plan.json describing CC and pitch_bend events per channel,
converts beat times to MIDI ticks, and merges them into the matching MIDI tracks
while preserving all existing events and correct delta-time ordering.
"""

import json
import os
import sys

import mido


def _find_track_for_channel(midi: mido.MidiFile, channel: int) -> int | None:
	"""Find the track index that contains messages for the given channel.

	Scans all tracks (skipping track 0 which is typically the tempo track)
	and returns the index of the first track that has a channel message
	matching the requested channel.
	"""
	for i, track in enumerate(midi.tracks):
		if i == 0:
			# Track 0 is conventionally the tempo/meta track
			continue
		for msg in track:
			if msg.type not in ('note_on', 'note_off', 'control_change',
								'program_change', 'pitchwheel',
								'polytouch', 'aftertouch'):
				continue
			if getattr(msg, 'channel', None) == channel:
				return i
	return None


def _track_to_absolute(track: mido.MidiTrack) -> list[tuple[int, mido.Message | mido.MetaMessage]]:
	"""Convert a track's delta-time messages to (absolute_tick, message) pairs."""
	result = []
	abs_tick = 0
	for msg in track:
		abs_tick += msg.time
		result.append((abs_tick, msg))
	return result


def _absolute_to_track(
	events: list[tuple[int, mido.Message | mido.MetaMessage]]
) -> mido.MidiTrack:
	"""Convert sorted (absolute_tick, message) pairs back to a MidiTrack with delta times."""
	track = mido.MidiTrack()
	prev_tick = 0
	for abs_tick, msg in events:
		delta = max(0, abs_tick - prev_tick)
		# Create a copy with the new delta time
		new_msg = msg.copy(time=delta)
		track.append(new_msg)
		prev_tick = abs_tick
	return track


def _create_plan_event(
	event: dict, channel: int, ticks_per_beat: int
) -> tuple[int, mido.Message]:
	"""Create a mido Message from a plan event dict.

	Returns (absolute_tick, message).
	"""
	time_beats = event['time_beats']
	abs_tick = int(time_beats * ticks_per_beat)
	event_type = event['type']

	if event_type == 'cc':
		msg = mido.Message(
			'control_change',
			channel=channel,
			control=event['control'],
			value=event['value'],
			time=0,  # Will be set by _absolute_to_track
		)
	elif event_type == 'pitch_bend':
		# Plan uses unsigned 0-16383; mido uses signed -8192..8191
		unsigned_pitch = event['value']
		signed_pitch = unsigned_pitch - 8192
		msg = mido.Message(
			'pitchwheel',
			channel=channel,
			pitch=signed_pitch,
			time=0,
		)
	else:
		raise ValueError(f"Unknown event type: {event_type}")

	return (abs_tick, msg)


def _convert_channels_format(plan: dict) -> list[dict]:
	"""Convert 'channels' format plan to 'tracks' format for uniform processing.

	The 'channels' format uses tick-based timing and groups CC by control number:
	  {"channels": {"1": {"cc_events": {"7": [{"tick": 0, "value": 100}, ...]}}}}

	The 'tracks' format uses beat-based timing:
	  {"tracks": [{"channel": 1, "events": [{"type": "cc", "time_beats": 0, ...}]}]}
	"""
	ticks_per_beat = plan.get('ppq', 480)
	tracks = []
	for ch_str, ch_data in plan.get('channels', {}).items():
		channel = int(ch_str)
		events = []
		for cc_num_str, cc_list in ch_data.get('cc_events', {}).items():
			cc_num = int(cc_num_str)
			for ev in cc_list:
				events.append({
					'type': 'cc',
					'time_beats': ev['tick'] / ticks_per_beat,
					'control': cc_num,
					'value': ev['value'],
				})
		if events:
			tracks.append({'channel': channel, 'events': events})
	return tracks


def _convert_sections_format(plan: dict, plan_path: str) -> list[dict]:
	"""Convert 'sections' format plan to 'tracks' format.

	The 'sections' format groups CC by section with per-channel values:
	  {"sections": [{"id": "A", "channels": {"0": {"cc7": 100, "cc11": 80}}}]}

	The 'tracks' format uses beat-based events:
	  {"tracks": [{"channel": 0, "events": [{"type": "cc", "time_beats": 0, ...}]}]}

	Requires plan.json to compute section beat ranges. Falls back to start_beat
	from section data if plan.json is not available.
	"""
	# Try to load plan.json for section beat ranges
	plan_dir = os.path.dirname(os.path.abspath(plan_path))
	plan_json_path = os.path.join(plan_dir, 'plan.json')
	section_beats = {}

	if os.path.isfile(plan_json_path):
		with open(plan_json_path, 'r', encoding='utf-8') as f:
			plan_json = json.load(f)
		section_beats = {
			s['id']: s.get('start_beat', 0) for s in plan_json.get('sections', [])
		}
		# Compute start_beat from cumulative measures if not set
		ts_str = plan_json.get('time_signature', '4/4')
		try:
			beats_per_measure = int(ts_str.split('/')[0])
		except (ValueError, IndexError):
			beats_per_measure = 4
		cumulative = 0
		for s in plan_json.get('sections', []):
			sid = s['id']
			if sid not in section_beats or (section_beats[sid] == 0 and cumulative > 0):
				section_beats[sid] = cumulative
			cumulative += s.get('measures', 0) * beats_per_measure

	# Map shorthand CC names to control numbers
	cc_name_map = {
		'cc7': 7, 'cc11': 11, 'cc1': 1, 'cc10': 10, 'cc64': 64, 'cc91': 91, 'cc93': 93,
	}

	tracks: dict[int, list[dict]] = {}

	for section in plan.get('sections', []):
		sid = section.get('id', '')
		start_beat = section_beats.get(sid, 0)
		channels = section.get('channels', {})

		for ch_str, ch_data in channels.items():
			channel = int(ch_str)
			if channel not in tracks:
				tracks[channel] = []

			for key, value in ch_data.items():
				if key in cc_name_map:
					tracks[channel].append({
						'type': 'cc',
						'time_beats': start_beat,
						'control': cc_name_map[key],
						'value': value,
					})
				elif key == 'pitch_bend':
					if isinstance(value, list):
						for pb_event in value:
							tracks[channel].append({
								'type': 'pitch_bend',
								'time_beats': start_beat + pb_event.get('offset_beats', 0),
								'value': pb_event['value'],
							})
					else:
						tracks[channel].append({
							'type': 'pitch_bend',
							'time_beats': start_beat,
							'value': value,
						})

	result = [{'channel': ch, 'events': events} for ch, events in tracks.items() if events]
	if not result:
		print(f"Warning: 'sections' format produced no events (plan: {plan_path})", file=sys.stderr)
	return result


def inject(base_midi_path: str, plan_path: str, output_path: str) -> None:
	"""Inject expression plan events into a base MIDI file.

	Supports three plan formats:
	- 'tracks' format: list of track dicts with beat-based events (preferred)
	- 'channels' format: dict of channel data with tick-based CC events
	- 'sections' format: per-section CC values (auto-converted, requires plan.json)

	Args:
		base_midi_path: Path to the input MIDI file.
		plan_path: Path to the expression_plan.json file.
		output_path: Path where the merged MIDI file will be saved.
	"""
	midi = mido.MidiFile(base_midi_path)

	with open(plan_path, 'r', encoding='utf-8') as f:
		plan = json.load(f)

	ticks_per_beat = midi.ticks_per_beat

	# Support 'tracks', 'channels', and 'sections' plan formats
	if 'tracks' in plan:
		track_plans = plan['tracks']
	elif 'channels' in plan:
		track_plans = _convert_channels_format(plan)
	elif 'sections' in plan:
		track_plans = _convert_sections_format(plan, plan_path)
	else:
		top_keys = list(plan.keys())[:5]
		print(
			f"Error: expression_plan.json has unrecognized format. "
			f"Expected top-level key 'tracks', 'channels', or 'sections', "
			f"but found: {top_keys}. No events injected.",
			file=sys.stderr,
		)
		track_plans = []

	for track_plan in track_plans:
		channel = track_plan['channel']
		track_idx = _find_track_for_channel(midi, channel)
		if track_idx is None:
			continue

		# Convert existing track to absolute time
		abs_events = _track_to_absolute(midi.tracks[track_idx])

		# Create new events from the plan
		for event in track_plan.get('events', []):
			new_event = _create_plan_event(event, channel, ticks_per_beat)
			abs_events.append(new_event)

		# Sort by absolute tick, preserving order for same-tick events
		# Sort by tick; CC/program_change before note events at same tick
		def _cc_first(pair):
			tick, msg = pair
			prio = 0 if msg.type in ('control_change', 'program_change', 'pitchwheel') else 1
			return (tick, prio)
		abs_events.sort(key=_cc_first)

		# Rebuild track with correct delta times
		midi.tracks[track_idx] = _absolute_to_track(abs_events)

	midi.save(output_path)


def analyze_balance(midi_path: str, plan_path: str) -> dict:
	"""Analyze voice overlap and compute CC7 balance adjustments.

	Reads the MIDI file and plan.json, For each non-drum voice, computes actual pitch range.
	For each pair with >5 semitone overlap, adjusts CC7 of lower-priority voice.

	Priority: melody > bass > harmony > drums.

	Returns dict with 'overlap_analysis' and 'cc7_adjustments'.
	"""
	midi = mido.MidiFile(midi_path)
	with open(plan_path, 'r', encoding='utf-8') as f:
		plan = json.load(f)

	orch = plan.get('orchestration', {})
	voice_order = ['melody', 'harmony', 'bass', 'drums']
	priority = {'melody': 0, 'bass': 1, 'harmony': 2, 'drums': 3}
	base_cc7 = {'melody': 100, 'bass': 85, 'harmony': 80}  # drums excluded

	# Collect actual pitch ranges per track
	voice_data: dict[int, dict] = {}
	for key in voice_order:
		if key == 'drums':
			continue  # drums don't get CC7 balance
		entry = orch.get(key, {})
		if not entry:
			continue
		channel = entry.get('channel', 0)
		track_idx = _find_track_for_channel(midi, channel)
		if track_idx is None:
			continue
		midi_notes = [m.note for m in midi.tracks[track_idx]
					 if m.type == 'note_on' and m.velocity > 0]
		if midi_notes:
			voice_data[channel] = {
				'key': key,
				'min_midi': min(midi_notes),
				'max_midi': max(midi_notes),
				'priority': priority.get(key, 3),
			}

	cc7 = {str(ch): base_cc7.get(d['key'], 85) for ch, d in voice_data.items()}

	# Pairwise overlap check
	overlap_analysis = []
	channels = list(voice_data.keys())
	for i in range(len(channels)):
		for j in range(i + 1, len(channels)):
				a, b = voice_data[channels[i]], voice_data[channels[j]]
				overlap_lo = max(a['min_midi'], b['min_midi'])
				overlap_hi = min(a['max_midi'], b['max_midi'])
				overlap = max(0, overlap_hi - overlap_lo)
				if overlap > 5:
					reduction = min(15, (overlap - 5) * 2)
					lower_ch = channels[i] if a['priority'] > b['priority'] else channels[j]
					cc7[str(lower_ch)] = max(50, cc7.get(str(lower_ch), 85) - reduction)
					overlap_analysis.append({
						'voices': [a['key'], b['key']],
						'overlap_semitones': overlap,
						'adjustment': -reduction if overlap > 7 else 0,
						'target_channel': lower_ch,
					})

	return {'overlap_analysis': overlap_analysis, 'cc7_adjustments': cc7}


def _compute_section_beats(plan: dict) -> list[dict]:
	"""Compute beat ranges for each section from plan.json.

	Uses 'start_beat' if present, otherwise derives from cumulative measures.
	Returns [{"id": "A", "start_beat": 0, "end_beat": 32, "balance_intent": "..."}, ...]
	"""
	ts_str = plan.get("time_signature", "4/4")
	try:
		beats_per_measure = int(ts_str.split("/")[0])
	except (ValueError, IndexError):
		beats_per_measure = 4

	sections = plan.get("sections", [])
	result = []
	cumulative = 0
	for sec in sections:
		start = sec.get("start_beat", cumulative)
		measures = sec.get("measures", 0)
		end = start + measures * beats_per_measure
		result.append({
			"id": sec.get("id", "?"),
			"name": sec.get("name", ""),
			"start_beat": start,
			"end_beat": end,
			"balance_intent": sec.get("balance_intent", ""),
		})
		cumulative = end
	return result


def _midi_note_name(midi: int) -> str:
	"""Convert MIDI note number to note name (e.g. 69 -> 'A4')."""
	names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
	octave = midi // 12 - 1
	return f"{names[midi % 12]}{octave}"


def analyze_balance_sections(midi_path: str, plan_path: str) -> dict:
	"""Per-section analysis of voice density and overlap.

	Returns objective data only — no CC7 suggestions.
	Decision-making is left to the Orchestrator agent.
	"""
	midi = mido.MidiFile(midi_path)
	with open(plan_path, 'r', encoding='utf-8') as f:
		plan = json.load(f)

	ticks_per_beat = midi.ticks_per_beat
	orch = plan.get('orchestration', {})
	voice_order = ['melody', 'harmony', 'bass', 'drums']

	# Map channel -> voice role with uniqueness check
	channel_role: dict[int, str] = {}
	seen_channels: set[int] = set()
	for key in voice_order:
		entry = orch.get(key, {})
		if entry:
			ch = entry.get('channel', 0)
			if ch in seen_channels:
				import sys
				print(f'Warning: duplicate channel {ch} for {key}', file=sys.stderr)
			seen_channels.add(ch)
			channel_role[ch] = key

	# Compute section beat ranges
	section_ranges = _compute_section_beats(plan)

	# Collect note events per track with absolute tick
	track_notes: dict[int, list[tuple[int, int, int]]] = {}  # channel -> [(abs_tick, midi_note, velocity)]
	for i, track in enumerate(midi.tracks):
		abs_tick = 0
		for msg in track:
			abs_tick += msg.time
			if msg.type == 'note_on' and msg.velocity > 0:
				ch = msg.channel
				if ch not in track_notes:
					track_notes[ch] = []
				track_notes[ch].append((abs_tick, msg.note, msg.velocity))

	# Sort notes by tick per channel
	for ch in track_notes:
		track_notes[ch].sort(key=lambda x: x[0])

	# Analyze per section
	sections_result = []
	for sec in section_ranges:
		start_tick = sec['start_beat'] * ticks_per_beat
		end_tick = sec['end_beat'] * ticks_per_beat
		section_beats = sec['end_beat'] - sec['start_beat']

		if section_beats <= 0:
			continue

		voices_data = {}
		for ch, role in channel_role.items():
			notes_in_section = [
				(midi_note, vel) for tick, midi_note, vel in track_notes.get(ch, [])
				if start_tick <= tick < end_tick
			]
			if not notes_in_section:
				continue

			midi_notes = [n for n, _ in notes_in_section]
			voices_data[role] = {
				'min_midi': min(midi_notes),
				'max_midi': max(midi_notes),
				'min_name': _midi_note_name(min(midi_notes)),
				'max_name': _midi_note_name(max(midi_notes)),
				'note_count': len(midi_notes),
				'density': round(len(midi_notes) / section_beats, 2),
			}

		# Pairwise overlap for non-drum voices
		overlaps = []
		non_drum = [r for r in voices_data if r != 'drums']
		for i in range(len(non_drum)):
			for j in range(i + 1, len(non_drum)):
				a = voices_data[non_drum[i]]
				b = voices_data[non_drum[j]]
				overlap_lo = max(a['min_midi'], b['min_midi'])
				overlap_hi = min(a['max_midi'], b['max_midi'])
				overlap = max(0, overlap_hi - overlap_lo)
				if overlap > 0:
					overlaps.append({
						'voices': [non_drum[i], non_drum[j]],
						'overlap_semitones': overlap,
					})

		sections_result.append({
			'section': sec['id'],
			'name': sec.get('name', ''),
			'start_beat': sec['start_beat'],
			'end_beat': sec['end_beat'],
			'balance_intent': sec.get('balance_intent', ''),
			'voices': voices_data,
			'overlaps': overlaps,
		})

	return {'sections': sections_result}


def _print_sections_chart(result: dict) -> None:
	"""Print ASCII charts for per-section balance analysis."""
	for sec in result.get('sections', []):
		intent_label = f" [{sec['balance_intent']}]" if sec.get('balance_intent') else ''
		print(f"\n  Section {sec['section']} - {sec.get('name', '')} "
			  f"(beats {sec['start_beat']}-{sec['end_beat']}){intent_label}:")

		voices = sec.get('voices', {})
		if not voices:
			print("    (no notes)")
			continue

		# Voice density bars
		max_density = max(v.get('density', 0) for v in voices.values()) if voices else 1
		bar_width = 20
		for role in ['melody', 'harmony', 'bass', 'drums']:
			if role not in voices:
				continue
			v = voices[role]
			bar_len = int(v['density'] / max_density * bar_width) if max_density > 0 else 0
			print(f"    {role:10s} {v['min_name']:>4s}-{v['max_name']:<4s} "
				  f"density: {v['density']:.2f}  {'#' * bar_len}{'.' * (bar_width - bar_len)}")

		# Overlap info
		overlaps = sec.get('overlaps', [])
		if overlaps:
			print(f"    overlaps:", end="")
			for ov in overlaps:
				marker = " (!)" if ov['overlap_semitones'] > 12 else ""
				print(f"  {'<->'.join(ov['voices'])} {ov['overlap_semitones']}st{marker}", end="")
			print()


def _print_balance_chart(result: dict) -> None:
	"""Print ASCII bar charts for balance analysis results."""
	# CC7 adjustments bar chart
	if result.get('cc7_adjustments'):
		print("\n  CC7 Balance Adjustments:")
		max_val = max(result['cc7_adjustments'].values()) if result['cc7_adjustments'] else 1
		bar_width = 30
		for ch, val in sorted(result['cc7_adjustments'].items(), key=lambda p: int(p[0])):
			bar_len = int(val / max_val * bar_width) if max_val > 0 else 0
			print(f"  Ch{ch}  {'#' * bar_len}{'.' * (bar_width - bar_len)}  {val}")

	# Overlap analysis
	if result.get('overlap_analysis'):
		print("\n  Voice Overlap:")
		for item in result['overlap_analysis']:
			voices = ' <-> '.join(item['voices'])
			overlap = item['overlap_semitones']
			bar_len = min(30, overlap)
			print(f"  {voices:20s}  {'#' * bar_len}{'.' * (30 - bar_len)}  {overlap} st")
			if item.get('adjustment', 0) != 0:
				print(f"  {' ':20s}  adjustment: {item['adjustment']} CC7 for Ch{item['target_channel']}")


def apply_balance(midi_path: str, plan_path: str, output_path: str) -> None:
	"""Apply CC7 balance adjustments at tick 0 for each channel."""
	balance = analyze_balance(midi_path, plan_path)
	midi = mido.MidiFile(midi_path)

	for ch_str, cc7_val in balance['cc7_adjustments'].items():
		channel = int(ch_str)
		track_idx = _find_track_for_channel(midi, channel)
		if track_idx is None:
			continue
		abs_events = _track_to_absolute(midi.tracks[track_idx])
		abs_events.append((0, mido.Message(
			'control_change', channel=channel, control=7, value=cc7_val, time=0,
		)))
		# Sort by tick; CC/program_change before note events at same tick
		def _cc_first(pair):
			tick, msg = pair
			prio = 0 if msg.type in ('control_change', 'program_change', 'pitchwheel') else 1
			return (tick, prio)
		abs_events.sort(key=_cc_first)
		midi.tracks[track_idx] = _absolute_to_track(abs_events)

	midi.save(output_path)


if __name__ == '__main__':
	import sys

	def print_usage():
		print("Usage:")
		print("  Inject expression:        python inject_expression.py <base.mid> <plan.json> <output.mid>")
		print("  Analyze balance (global): python inject_expression.py <base.mid> --balance <plan.json> [-o balance.json]")
		print("  Analyze balance (section):python inject_expression.py <base.mid> --balance-sections <plan.json> [-o sections.json]")
		print("  Apply balance:            python inject_expression.py <base.mid> --apply-balance <plan.json> <output.mid>")

	if len(sys.argv) < 2:
		print_usage()
		sys.exit(1)

	args = sys.argv[1:]

	if '--balance' in args:
		idx = args.index('--balance')
		midi_path = args[idx - 1] if idx > 0 else None
		plan_path = args[idx + 1] if idx + 1 < len(args) else None
		if not midi_path or not plan_path:
			print("Error: --balance requires <base.mid> <plan.json>")
			sys.exit(1)
		output_json = None
		if '-o' in args:
			o_idx = args.index('-o')
			output_json = args[o_idx + 1]
		result = analyze_balance(midi_path, plan_path)
		_print_balance_chart(result)
		if output_json:
			with open(output_json, 'w', encoding='utf-8') as f:
				json.dump(result, f, indent=2, ensure_ascii=False)
			print(f"Balance analysis saved to {output_json}")
		else:
			print(json.dumps(result, indent=2, ensure_ascii=False))
	elif '--balance-sections' in args:
		idx = args.index('--balance-sections')
		midi_path = args[idx - 1] if idx > 0 else None
		plan_path = args[idx + 1] if idx + 1 < len(args) else None
		if not midi_path or not plan_path:
			print("Error: --balance-sections requires <base.mid> <plan.json>")
			sys.exit(1)
		output_json = None
		if '-o' in args:
			o_idx = args.index('-o')
			output_json = args[o_idx + 1]
		result = analyze_balance_sections(midi_path, plan_path)
		_print_sections_chart(result)
		if output_json:
			with open(output_json, 'w', encoding='utf-8') as f:
				json.dump(result, f, indent=2, ensure_ascii=False)
			print(f"Section balance saved to {output_json}")
		else:
			print(json.dumps(result, indent=2, ensure_ascii=False))
	elif '--apply-balance' in args:
		idx = args.index('--apply-balance')
		midi_path = args[idx - 1] if idx > 0 else None
		plan_path = args[idx + 1] if idx + 1 < len(args) else None
		output_path = args[idx + 2] if idx + 2 < len(args) else None
		if not all([midi_path, plan_path, output_path]):
			print("Error: --apply-balance requires <base.mid> <plan.json> <output.mid>")
			sys.exit(1)
		apply_balance(midi_path, plan_path, output_path)
		print(f"Balance applied, saved to {output_path}")
	elif len(args) >= 3:
		inject(args[0], args[1], args[2])
		print(f"Expression injected, saved to {args[2]}")
	else:
		print_usage()
		sys.exit(1)
