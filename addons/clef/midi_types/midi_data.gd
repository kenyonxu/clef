## MIDI 文件数据

class_name MidiData
extends RefCounted

var tempo: int = 120
var timebase: int = 480
var tracks: Array[TrackData] = []
## 速度变化事件: [{time_ticks: int, bpm: int}]
var tempo_events: Array[Dictionary] = []
## CC 控制变化事件: [{time_ticks: int, channel: int, controller: int, value: int}]
var cc_events: Array[Dictionary] = []
## Pitch Bend 弯音事件: [{time_ticks: int, channel: int, value: int}]
var pitch_bend_events: Array[Dictionary] = []
## Program Change 乐器切换事件: [{time_ticks: int, channel: int, preset_index: int}]
var program_events: Array[Dictionary] = []

func _init(p_tempo: int = 120, p_tracks: Array[TrackData] = [], p_timebase: int = 480, p_tempo_events: Array[Dictionary] = [], p_cc_events: Array[Dictionary] = [], p_pitch_bend_events: Array[Dictionary] = [], p_program_events: Array[Dictionary] = []) -> void:
	tempo = p_tempo
	tracks = p_tracks
	timebase = p_timebase
	tempo_events = p_tempo_events
	cc_events = p_cc_events
	pitch_bend_events = p_pitch_bend_events
	program_events = p_program_events
