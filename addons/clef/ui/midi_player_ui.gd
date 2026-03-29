## MIDI 播放器进度 UI — 进度条 + 时间显示 + 播放/暂停/停止控制
class_name MidiPlayerUI
extends Control

@export var player: MidiStreamPlayer : set = set_player

@onready var _play_button: Button = %PlayButton
@onready var _stop_button: Button = %StopButton
@onready var _slider: HSlider = %ProgressSlider
@onready var _time_label: Label = %TimeLabel

var _is_seeking: bool = false


func _ready() -> void:
	if _play_button:
		_play_button.pressed.connect(_on_play_pressed)
	if _stop_button:
		_stop_button.pressed.connect(_on_stop_pressed)
	if _slider:
		_slider.drag_started.connect(func() -> void: _is_seeking = true)
		_slider.drag_ended.connect(_on_slider_drag_ended)
		_slider.value_changed.connect(_on_slider_value_changed)
	if player:
		_connect_player_signals()
	_update_display(0.0, 0.0)


func _exit_tree() -> void:
	_disconnect_player_signals()


func set_player(value: MidiStreamPlayer) -> void:
	if player == value:
		return
	if player:
		_disconnect_player_signals()
	player = value
	if player:
		_connect_player_signals()


func _connect_player_signals() -> void:
	if not player.progress_updated.is_connected(_on_progress_updated):
		player.progress_updated.connect(_on_progress_updated)
	if not player.finished.is_connected(_on_player_finished):
		player.finished.connect(_on_player_finished)


func _disconnect_player_signals() -> void:
	if player:
		if player.progress_updated.is_connected(_on_progress_updated):
			player.progress_updated.disconnect(_on_progress_updated)
		if player.finished.is_connected(_on_player_finished):
			player.finished.disconnect(_on_player_finished)


func _on_progress_updated(position: float, duration: float) -> void:
	if _is_seeking:
		return
	_update_display(position, duration)
	if _slider and duration > 0.0:
		_slider.max_value = duration
		_slider.value = position
	_sync_button_state()


func _update_display(position: float, duration: float) -> void:
	if _time_label:
		_time_label.text = "%s / %s" % [
			MidiStreamPlayer.format_time(position),
			MidiStreamPlayer.format_time(duration),
		]


func _sync_button_state() -> void:
	if not _play_button or not player:
		return
	if player.is_playing():
		_play_button.text = "⏸"
	else:
		_play_button.text = "▶"


func _on_play_pressed() -> void:
	if not player:
		return
	if player.is_playing():
		player.pause()
		if _play_button:
			_play_button.text = "▶"
	else:
		if player.is_paused():
			player.resume()
		else:
			player.start_playback()
		if _play_button:
			_play_button.text = "⏸"


func _on_stop_pressed() -> void:
	if not player:
		return
	player.stop()
	if _slider:
		_slider.value = 0.0
	_update_display(0.0, player.get_duration())
	_sync_button_state()


func _on_slider_drag_ended(value: float) -> void:
	_is_seeking = false
	if player:
		var duration: float = player.get_duration()
		player.seek(clampf(value, 0.0, duration))


func _on_slider_value_changed(value: float) -> void:
	# 拖拽中仅更新时间标签，不 seek
	if _is_seeking and _slider:
		_update_display(value, _slider.max_value)


func _on_player_finished() -> void:
	if _slider:
		_slider.value = 0.0
	_update_display(0.0, player.get_duration() if player else 0.0)
	_sync_button_state()
