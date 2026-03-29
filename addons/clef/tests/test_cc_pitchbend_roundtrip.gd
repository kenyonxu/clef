extends SceneTree

func _init() -> void:
	print("\n=== CC / Pitch Bend Round-trip Test ===")

	# 构建包含 CC 和 Pitch Bend 的 MidiData
	var midi_data := MidiData.new(120, [
		TrackData.new("Test", 0, 0, [
			NoteData.new(60, 0, 480, 100),
			NoteData.new(64, 480, 480, 80),
		], [
			{"time_ticks": 0, "controller": 7, "value": 80},
			{"time_ticks": 0, "controller": 10, "value": 64},
			{"time_ticks": 960, "controller": 11, "value": 100},
			{"time_ticks": 960, "controller": 1, "value": 64},
		], [
			{"time_ticks": 0, "value": 8192},
			{"time_ticks": 480, "value": 9000},
		]),
	])

	var bytes: PackedByteArray = MidiWriter.encode(midi_data)
	print("Encoded %d bytes" % bytes.size())

	var result := MidiReader.from_bytes(bytes)
	if not result.ok:
		print("FAIL: parse error: %s" % result.error_message)
		quit(1)
		return

	# 验证音符
	var notes = result.midi_data.tracks[0].notes
	if notes.size() != 2:
		print("FAIL: expected 2 notes, got %d" % notes.size())
		quit(1)
		return
	if notes[0].pitch != 60 or notes[0].velocity != 100:
		print("FAIL: note 0 mismatch")
		quit(1)
		return
	if notes[1].pitch != 64 or notes[1].velocity != 80:
		print("FAIL: note 1 mismatch")
		quit(1)
		return
	print("PASS: notes round-trip")

	# 验证全局 CC 事件
	var cc = result.midi_data.cc_events
	if cc.size() != 4:
		print("FAIL: expected 4 CC events, got %d" % cc.size())
		quit(1)
		return
	if cc[0]["controller"] != 7 or cc[0]["value"] != 80:
		print("FAIL: CC7 mismatch")
		quit(1)
		return
	if cc[1]["controller"] != 10 or cc[1]["value"] != 64:
		print("FAIL: CC10 mismatch")
		quit(1)
		return
	if cc[2]["controller"] != 11 or cc[2]["value"] != 100:
		print("FAIL: CC11 mismatch")
		quit(1)
		return
	if cc[3]["controller"] != 1 or cc[3]["value"] != 64:
		print("FAIL: CC1 mismatch")
		quit(1)
		return
	print("PASS: CC events round-trip")

	# 验证全局 Pitch Bend 事件
	var pb = result.midi_data.pitch_bend_events
	if pb.size() != 2:
		print("FAIL: expected 2 Pitch Bend events, got %d" % pb.size())
		quit(1)
		return
	if pb[0]["value"] != 8192:
		print("FAIL: Pitch Bend center expected 8192, got %d" % pb[0]["value"])
		quit(1)
		return
	if pb[1]["value"] != 9000:
		print("FAIL: Pitch Bend up expected 9000, got %d" % pb[1]["value"])
		quit(1)
		return
	print("PASS: Pitch Bend events round-trip")

	# 验证轨道级 CC/Pitch Bend
	var track_cc = result.midi_data.tracks[0].cc_events
	if track_cc.size() != 4:
		print("FAIL: track CC expected 4, got %d" % track_cc.size())
		quit(1)
		return
	print("PASS: track-level CC events")

	var track_pb = result.midi_data.tracks[0].pitch_bend_events
	if track_pb.size() != 2:
		print("FAIL: track Pitch Bend expected 2, got %d" % track_pb.size())
		quit(1)
		return
	print("PASS: track-level Pitch Bend events")

	# 向后兼容: 无 CC/PB 的旧格式
	var simple_data := MidiData.new(120, [
		TrackData.new("Simple", 0, 0, [NoteData.new(60, 0, 480, 100)]),
	])
	var simple_bytes: PackedByteArray = MidiWriter.encode(simple_data)
	var simple_result := MidiReader.from_bytes(simple_bytes)
	if not simple_result.ok:
		print("FAIL: simple parse error")
		quit(1)
		return
	if simple_result.midi_data.cc_events.size() != 0 or simple_result.midi_data.pitch_bend_events.size() != 0:
		print("FAIL: simple MIDI should have 0 CC/PB events")
		quit(1)
		return
	if simple_result.midi_data.tracks[0].notes.size() != 1:
		print("FAIL: simple MIDI note mismatch")
		quit(1)
		return
	print("PASS: backward compatibility")

	# MidiResource 往返
	var res := MidiResource.new()
	res.from_midi_data(result.midi_data)
	var restored: MidiData = res.get_midi_data()
	if restored.cc_events.size() != 4:
		print("FAIL: MidiResource CC round-trip")
		quit(1)
		return
	if restored.pitch_bend_events.size() != 2:
		print("FAIL: MidiResource Pitch Bend round-trip")
		quit(1)
		return
	print("PASS: MidiResource round-trip")

	print("\nPASS: All tests")
	quit(0)
