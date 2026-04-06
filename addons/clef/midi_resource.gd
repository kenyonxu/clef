## MIDI 资源类型，Godot 原生 Resource
## 可在 Inspector 中查看/编辑，保存为 .tres

class_name MidiResource
extends Resource

@export_category("MIDI Data")
@export var tempo: int = 120
@export var timebase: int = 480
@export var tracks: Array[TrackResource] = []
@export var tempo_events: Array[Dictionary] = []
## CC 控制变化事件: [{time_ticks: int, channel: int, controller: int, value: int}]
@export var cc_events: Array[Dictionary] = []
## Pitch Bend 弯音事件: [{time_ticks: int, channel: int, value: int}]
@export var pitch_bend_events: Array[Dictionary] = []
## Program Change 乐器切换事件: [{time_ticks: int, channel: int, preset_index: int}]
@export var program_events: Array[Dictionary] = []


func from_midi_data(data: MidiData) -> void:
	tempo = data.tempo
	timebase = data.timebase
	tempo_events = data.tempo_events.duplicate(true)
	cc_events = data.cc_events.duplicate(true)
	pitch_bend_events = data.pitch_bend_events.duplicate(true)
	program_events = data.program_events.duplicate(true)
	tracks.clear()
	for track_data in data.tracks:
		var track_res := TrackResource.new()
		track_res.name = track_data.name
		track_res.resource_name = track_data.name
		track_res.channel = track_data.channel
		track_res.instrument = track_data.instrument
		track_res.cc_events = track_data.cc_events.duplicate(true)
		track_res.pitch_bend_events = track_data.pitch_bend_events.duplicate(true)
		for note_data in track_data.notes:
			var note_res := NoteResource.new()
			note_res.pitch = note_data.pitch
			note_res.start_ticks = note_data.start_ticks
			note_res.duration_ticks = note_data.duration_ticks
			note_res.velocity = note_data.velocity
			track_res.notes.append(note_res)
		tracks.append(track_res)


func get_midi_data() -> MidiData:
	var track_list: Array[TrackData] = []
	for track_res in tracks:
		var note_list: Array[NoteData] = []
		for note_res in track_res.notes:
			note_list.append(NoteData.new(
				note_res.pitch, note_res.start_ticks,
				note_res.duration_ticks, note_res.velocity
			))
		track_list.append(TrackData.new(
			track_res.name, track_res.channel,
			track_res.instrument, note_list,
			track_res.cc_events.duplicate(true),
			track_res.pitch_bend_events.duplicate(true)
		))
	return MidiData.new(tempo, track_list, timebase, tempo_events.duplicate(true), cc_events.duplicate(true), pitch_bend_events.duplicate(true), program_events.duplicate(true))


func get_duration_seconds() -> float:
	if tracks.is_empty():
		return 0.0
	var max_end_ticks: int = 0
	var ticks_per_second: float = float(tempo) / 60.0 * float(timebase)
	for track in tracks:
		for note in track.notes:
			var end_ticks: int = note.start_ticks + note.duration_ticks
			if end_ticks > max_end_ticks:
				max_end_ticks = end_ticks
	return float(max_end_ticks) / ticks_per_second


func get_track_count() -> int:
	return tracks.size()


func from_json_string(json: String) -> bool:
	var result := MidiComposerConverter.from_json_string(json)
	if not result.ok:
		return false
	from_midi_data(result.midi_data)
	return true
