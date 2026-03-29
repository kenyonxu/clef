## 音轨数据

class_name TrackData
extends RefCounted

var name: String = ""
var channel: int = 0
var instrument: int = 0
var notes: Array[NoteData] = []
## CC 控制变化事件: [{time_ticks: int, controller: int, value: int}]
var cc_events: Array[Dictionary] = []
## Pitch Bend 弯音事件: [{time_ticks: int, value: int}]
var pitch_bend_events: Array[Dictionary] = []

func _init(p_name: String = "", p_channel: int = 0, p_instrument: int = 0, p_notes: Array[NoteData] = [], p_cc_events: Array[Dictionary] = [], p_pitch_bend_events: Array[Dictionary] = []) -> void:
	name = p_name
	channel = p_channel
	instrument = p_instrument
	notes = p_notes
	cc_events = p_cc_events
	pitch_bend_events = p_pitch_bend_events
