extends SceneTree

func _init() -> void:
	print("\n=== MidiReader Quick Test ===")

	# Test round-trip: encode then parse
	var midi_data := MidiData.new(140, [
		TrackData.new("Test", 0, 0, [
			NoteData.new(60, 0, 480, 100),
			NoteData.new(64, 480, 480, 100),
		]),
	])
	var bytes: PackedByteArray = MidiWriter.encode(midi_data)
	print("Encoded %d bytes" % bytes.size())

	var result := MidiReader.from_bytes(bytes)
	if not result.ok:
		print("FAIL: %s" % result.error_message)
		quit(1)
		return

	if result.midi_data.tempo != 140:
		print("FAIL: tempo expected 140, got %d" % result.midi_data.tempo)
		quit(1)
		return

	if result.midi_data.tracks.size() != 1:
		print("FAIL: tracks expected 1, got %d" % result.midi_data.tracks.size())
		quit(1)
		return

	var notes = result.midi_data.tracks[0].notes
	if notes.size() != 2:
		print("FAIL: notes expected 2, got %d" % notes.size())
		quit(1)
		return

	if notes[0].pitch != 60 or notes[0].start_ticks != 0:
		print("FAIL: note 0 mismatch")
		quit(1)
		return

	print("PASS: Round-trip test")
	print("PASS: All tests")
	quit(0)
