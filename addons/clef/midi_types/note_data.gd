## 音符数据

class_name NoteData
extends RefCounted

var pitch: int = 60
var start_ticks: int = 0
var duration_ticks: int = 480
var velocity: int = 100

func _init(p_pitch: int = 60, p_start_ticks: int = 0, p_duration_ticks: int = 480, p_velocity: int = 100) -> void:
	pitch = p_pitch
	start_ticks = p_start_ticks
	duration_ticks = p_duration_ticks
	velocity = p_velocity
