## 音轨资源（Inspector 可编辑）

class_name TrackResource
extends Resource

@export var name: String = ""
@export var channel: int = 0
@export var instrument: int = 0
@export var notes: Array[NoteResource] = []
## CC 控制变化事件: [{time_ticks: int, controller: int, value: int}]
@export var cc_events: Array[Dictionary] = []
## Pitch Bend 弯音事件: [{time_ticks: int, value: int}]
@export var pitch_bend_events: Array[Dictionary] = []
