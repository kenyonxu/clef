## 编辑器与运行时 MidiStreamPlayer 的桥接
## 作为插件内部子节点管理，转发 MidiStreamPlayer 信号供面板使用
extends RefCounted

signal player_changed(player: MidiStreamPlayer)
signal player_connected(player: MidiStreamPlayer)
signal player_disconnected(player: MidiStreamPlayer)

## 转发信号（供面板连接）
signal midi_note_on(channel: int, pitch: int, velocity: int)
signal midi_note_off(channel: int, pitch: int)
signal midi_cc(channel: int, controller: int, value: int)
signal midi_pitch_bend(channel: int, value: int)
signal midi_program_change(channel: int, preset_index: int)

var current_player: MidiStreamPlayer = null : set = set_current_player
var _connected_players: Array[MidiStreamPlayer] = []


func set_current_player(player: MidiStreamPlayer) -> void:
	if current_player == player:
		return
	_disconnect_player(current_player)
	current_player = player
	player_changed.emit(player)
	if player != null:
		_connect_player(player)


func _connect_player(player: MidiStreamPlayer) -> void:
	if player == null or player in _connected_players:
		return
	player.note_triggered.connect(_on_note_triggered)
	player.note_released.connect(_on_note_released)
	player.cc_received.connect(_on_cc_received)
	player.pitch_bend_received.connect(_on_pitch_bend_received)
	player.program_changed.connect(_on_program_changed)
	_connected_players.append(player)
	player_connected.emit(player)


func _disconnect_player(player: MidiStreamPlayer) -> void:
	if player == null or player not in _connected_players:
		return
	if player.note_triggered.is_connected(_on_note_triggered):
		player.note_triggered.disconnect(_on_note_triggered)
	if player.note_released.is_connected(_on_note_released):
		player.note_released.disconnect(_on_note_released)
	if player.cc_received.is_connected(_on_cc_received):
		player.cc_received.disconnect(_on_cc_received)
	if player.pitch_bend_received.is_connected(_on_pitch_bend_received):
		player.pitch_bend_received.disconnect(_on_pitch_bend_received)
	if player.program_changed.is_connected(_on_program_changed):
		player.program_changed.disconnect(_on_program_changed)
	_connected_players.erase(player)
	player_disconnected.emit(player)


func _on_note_triggered(ch: int, pitch: int, vel: int) -> void:
	midi_note_on.emit(ch, pitch, vel)


func _on_note_released(ch: int, pitch: int) -> void:
	midi_note_off.emit(ch, pitch)


func _on_cc_received(ch: int, ctrl: int, val: int) -> void:
	midi_cc.emit(ch, ctrl, val)


func _on_pitch_bend_received(ch: int, val: int) -> void:
	midi_pitch_bend.emit(ch, val)


func _on_program_changed(ch: int, preset: int) -> void:
	midi_program_change.emit(ch, preset)
