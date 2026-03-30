## 编辑器 MIDI 播放器 — 包装 MidiStreamPlayer 用于编辑器内预览
@tool
class_name EditorPlayer
extends RefCounted

signal file_loaded(path: String, duration: float)
signal load_failed(path: String, error: String)

var _player: MidiStreamPlayer = null
var _host_node: Node = null
var _bridge: RefCounted = null
var _current_path: String = ""


func setup(host_node: Node, bridge: RefCounted) -> void:
	_host_node = host_node
	_bridge = bridge


func load_file(path: String) -> bool:
	_unload()

	if not FileAccess.file_exists(path):
		load_failed.emit(path, "File not found")
		return false

	var midi_res: MidiResource = null

	if path.ends_with(".tres"):
		midi_res = load(path) as MidiResource
		if midi_res == null:
			load_failed.emit(path, "Failed to load .tres")
			return false
	elif path.ends_with(".mid"):
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null:
			load_failed.emit(path, "Cannot read file")
			return false
		var bytes := file.get_buffer(file.get_length())
		file.close()
		var result := MidiReader.from_bytes(bytes)
		if not result.ok:
			load_failed.emit(path, result.error_message)
			return false
		midi_res = MidiResource.new()
		midi_res.from_midi_data(result.midi_data)
	elif path.ends_with(".json"):
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null:
			load_failed.emit(path, "Cannot read file")
			return false
		var result := MidiComposerConverter.from_json_string(file.get_as_text())
		file.close()
		if not result.ok:
			load_failed.emit(path, result.error_message)
			return false
		midi_res = MidiResource.new()
		midi_res.from_midi_data(result.midi_data)
	else:
		load_failed.emit(path, "Unsupported format")
		return false

	_player = MidiStreamPlayer.new()
	_player.name = "EditorMidiPlayer"
	_player._editor_preview = true
	_player.midi_resource = midi_res
	_player.soundfont = ProjectSettings.get_setting("clef/default_soundfont", "")
	_player.volume_db = -12.0
	# 添加到场景根节点，避免 editor main screen 的 viewport 问题
	Engine.get_main_loop().root.add_child(_player)

	_current_path = path
	await _host_node.get_tree().process_frame
	var duration: float = 0.0
	if midi_res != null and midi_res.has_method("get_duration_seconds"):
		duration = midi_res.get_duration_seconds()
	if duration <= 0.0:
		duration = _player.get_duration()
	if _bridge != null:
		_bridge.set_current_player(_player)
	file_loaded.emit(path, duration)
	return true


func play() -> void:
	if _player == null:
		return
	if _player.is_paused():
		_player.resume()
	else:
		_player.start_playback()


func stop() -> void:
	if _player == null:
		return
	_player.stop()


func pause() -> void:
	if _player == null:
		return
	_player.pause()


func seek(position: float) -> void:
	if _player == null:
		return
	_player.seek(position)


func is_playing() -> bool:
	return _player != null and _player.is_playing()


func is_paused() -> bool:
	return _player != null and _player.is_paused()


func get_position() -> float:
	if _player == null:
		return 0.0
	return _player.get_playback_position()


func get_duration() -> float:
	if _player == null:
		return 0.0
	return _player.get_duration()


func set_channel_volume(channel: int, vol: float) -> void:
	if _player == null:
		return
	if _player.has_method("set_channel_volume"):
		_player.set_channel_volume(channel, vol)


func set_channel_mute(channel: int, muted: bool) -> void:
	if _player == null:
		return
	if _player.has_method("set_channel_mute"):
		_player.set_channel_mute(channel, muted)


func set_master_volume(volume_db: float) -> void:
	if _player == null:
		return
	_player.volume_db = volume_db


func get_master_volume() -> float:
	if _player == null:
		return -80.0
	return _player.volume_db


func _unload() -> void:
	if _player != null:
		_player.stop()
		if _bridge != null:
			_bridge.set_current_player(null)
		_player.queue_free()
		_player = null
	_current_path = ""
