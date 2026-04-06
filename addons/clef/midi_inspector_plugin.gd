@tool
class_name MidiInspectorPlugin
extends EditorInspectorPlugin

var _current_object: MidiResource = null
var _player: MidiStreamPlayer = null
var _play_button: Button = null
var _stop_button: Button = null
var _progress_slider: HSlider = null
var _pause_button: Button = null
var _time_label: Label = null
var _export_button: Button = null
var _progress_timer: Timer = null
var _container: HBoxContainer = null
var _export_container: HBoxContainer = null
var _preview_control: Control = null
var l10n: ClefL10n

const _PREVIEW_HEIGHT: float = 88.0


func _can_handle(object: Object) -> bool:
	return object is MidiResource


## _parse_begin 在所有属性之前调用 — 放置迷你预览和播放控制
func _parse_begin(object: Object) -> void:
	# 切换对象时停止播放
	if object != _current_object and _player != null:
		_stop_playback()
	_current_object = object as MidiResource

	# 释放旧控件
	if _preview_control:
		_preview_control.queue_free()
		_preview_control = null
	if _container:
		_container.queue_free()
		_container = null

	if not _current_object:
		return

	# ── 迷你钢琴卷帘预览 ──
	_preview_control = Control.new()
	_preview_control.custom_minimum_size.y = _PREVIEW_HEIGHT
	_preview_control.draw.connect(_draw_mini_preview)
	add_custom_control(_preview_control)

	# ── 播放控制行 ──
	var sf2_path: String = ProjectSettings.get_setting(
		"clef/default_soundfont", "")
	if sf2_path == "":
		sf2_path = _current_object.preview_soundfont if _current_object.has_method("get") else ""

	_container = HBoxContainer.new()

	_play_button = Button.new()
	_play_button.text = "▶ " + l10n.t("Play")
	_play_button.tooltip_text = l10n.t("Preview MIDI playback")
	_play_button.disabled = sf2_path == ""
	_play_button.pressed.connect(_on_play_pressed)
	_container.add_child(_play_button)

	_stop_button = Button.new()
	_stop_button.text = "⏹ " + l10n.t("Stop")
	_stop_button.tooltip_text = l10n.t("Stop")
	_stop_button.disabled = true
	_stop_button.pressed.connect(_on_stop_pressed)
	_container.add_child(_stop_button)

	_pause_button = Button.new()
	_pause_button.text = "⏸"
	_pause_button.tooltip_text = l10n.t("Pause")
	_pause_button.disabled = true
	_pause_button.pressed.connect(_on_pause_pressed)
	_container.add_child(_pause_button)

	_progress_slider = HSlider.new()
	_progress_slider.custom_minimum_size.x = 150
	_progress_slider.max_value = 1.0
	_progress_slider.value = 0.0
	_progress_slider.step = 0.01
	_progress_slider.min_value = 0.0
	_progress_slider.drag_ended.connect(_on_slider_drag_ended)
	_container.add_child(_progress_slider)

	_time_label = Label.new()
	_time_label.text = "0:00 / 0:00"
	_time_label.custom_minimum_size.x = 80
	_time_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_container.add_child(_time_label)

	if sf2_path == "":
		var label := Label.new()
		label.text = l10n.t("Please configure default Soundfont")
		label.add_theme_color_override("font_color", Color(1.0, 0.6, 0.3, 1.0))
		_container.add_child(label)

	add_custom_control(_container)


## _parse_end 在所有属性之后调用 — 仅放置导出按钮
func _parse_end(object: Object) -> void:
	if _export_container:
		_export_container.queue_free()
		_export_container = null

	if not _current_object:
		return

	# ── 导出行 ──
	_export_container = HBoxContainer.new()

	_export_button = Button.new()
	_export_button.text = l10n.t("Export JSON")
	_export_button.tooltip_text = l10n.t("Export MIDI resource to Clef JSON v2.0 format (for LLM composition)")
	_export_button.pressed.connect(_on_export_json_pressed)
	_export_container.add_child(_export_button)

	add_custom_control(_export_container)


# ─── 迷你钢琴卷帘绘制 ─────────────────────────────────────

func _draw_mini_preview() -> void:
	if _current_object == null or _preview_control == null:
		return
	var ctrl: Control = _preview_control
	var rect: Rect2 = ctrl.get_rect()
	if rect.size.x < 20 or rect.size.y < 20:
		return

	# 背景
	ctrl.draw_rect(rect, Color(0.1, 0.1, 0.14))

	# 计算音符范围
	var t_min: int = 0
	var t_max: int = 1
	var p_min: int = 127
	var p_max: int = 0

	for track in _current_object.tracks:
		for note in track.notes:
			if note.start_ticks < t_min:
				t_min = note.start_ticks
			var end_t: int = note.start_ticks + note.duration_ticks
			if end_t > t_max:
				t_max = end_t
			if note.pitch < p_min:
				p_min = note.pitch
			if note.pitch > p_max:
				p_max = note.pitch

	if t_max <= t_min:
		t_max = t_min + 1
	if p_max < p_min:
		p_max = p_min + 1

	var margin := 3.0
	var draw_area := Rect2(
		margin, margin,
		rect.size.x - margin * 2, rect.size.y - margin * 2
	)
	var t_range: float = float(t_max - t_min)
	var p_range: float = float(p_max - p_min + 1)

	# 绘制八度分隔线（C 音位置）
	for octave in range(0, 11):
		var pitch: int = octave * 12
		if pitch < p_min or pitch > p_max:
			continue
		var y: float = draw_area.end.y - (float(pitch - p_min) / p_range) * draw_area.size.y
		ctrl.draw_line(
			Vector2(draw_area.position.x, y),
			Vector2(draw_area.end.x, y),
			Color(0.25, 0.25, 0.3), 0.5
		)

	# 绘制音符
	for track in _current_object.tracks:
		var ch: int = track.channel
		var color: Color = ChannelColors.COLORS[ch % 16] if ch < 16 else Color(0.7, 0.7, 0.7)
		for note in track.notes:
			var vel_factor: float = 0.5 + 0.5 * (float(note.velocity) / 127.0)
			var note_color := Color(
				color.r * vel_factor,
				color.g * vel_factor,
				color.b * vel_factor,
				0.85
			)
			var x: float = draw_area.position.x + (float(note.start_ticks - t_min) / t_range) * draw_area.size.x
			var w: float = maxf((float(note.duration_ticks) / t_range) * draw_area.size.x, 1.0)
			var note_y: float = draw_area.end.y - (float(note.pitch - p_min + 1) / p_range) * draw_area.size.y
			var h: float = maxf(draw_area.size.y / p_range, 1.5)
			ctrl.draw_rect(Rect2(x, note_y, w, h), note_color)

	# 绘制播放进度线（使用进度滑块的值，与播放状态同步）
	if _progress_slider and _progress_slider.value > 0.001:
		var progress: float = clampf(_progress_slider.value, 0.0, 1.0)
		var px: float = draw_area.position.x + progress * draw_area.size.x
		ctrl.draw_line(
			Vector2(px, draw_area.position.y),
			Vector2(px, draw_area.end.y),
			Color(1, 1, 1, 0.9), 2.0
		)

	# 边框
	ctrl.draw_rect(rect, Color(0.25, 0.25, 0.3), false, 1.0)


# ─── 播放控制 ─────────────────────────────────────────────

func _on_play_pressed() -> void:
	if _current_object == null:
		return
	var sf2_path: String = ProjectSettings.get_setting(
		"clef/default_soundfont", "")

	_stop_playback()

	_player = MidiStreamPlayer.new()
	_player.midi_resource = _current_object
	_player.soundfont = sf2_path
	_player._editor_preview = true
	_player.finished.connect(_on_playback_finished)
	EditorInterface.get_base_control().add_child(_player)
	_player.start_playback()

	_progress_timer = Timer.new()
	_progress_timer.wait_time = 0.1
	_progress_timer.timeout.connect(_update_progress)
	EditorInterface.get_base_control().add_child(_progress_timer)
	_progress_timer.start()

	if _play_button:
		_play_button.disabled = true
	if _stop_button:
		_stop_button.disabled = false
	if _pause_button:
		_pause_button.disabled = false


func _on_stop_pressed() -> void:
	_stop_playback()


func _on_pause_pressed() -> void:
	if _player == null:
		return
	if _player.is_paused():
		_player.resume()
		if _pause_button:
			_pause_button.text = "⏸"
	else:
		_player.pause()
		if _pause_button:
			_pause_button.text = "▶"


func _on_slider_drag_ended(value: float) -> void:
	if _player == null:
		return
	var duration: float = _player.get_duration()
	if duration > 0.0:
		_player.seek(clampf(value * duration, 0.0, duration))


func _stop_playback() -> void:
	if _player != null:
		_player.finished.disconnect(_on_playback_finished)
		_player.stop()
		_player.queue_free()
		_player = null
	if _play_button:
		_play_button.disabled = false
	if _stop_button:
		_stop_button.disabled = true
	if _pause_button:
		_pause_button.disabled = true
		_pause_button.text = "⏸"
	if _progress_slider:
		_progress_slider.value = 0.0
	if _time_label:
		_time_label.text = "0:00 / 0:00"
	if _progress_timer != null:
		_progress_timer.stop()
		_progress_timer.queue_free()
		_progress_timer = null
	if _preview_control:
		_preview_control.queue_redraw()


func _on_playback_finished() -> void:
	_stop_playback()


func _update_progress() -> void:
	if _player != null and _progress_slider != null and _player.is_playing():
		var position: float = _player.get_playback_position()
		var duration: float = _player.get_duration()
		if duration > 0.0:
			_progress_slider.value = clampf(position / duration, 0.0, 1.0)
		if _time_label:
			_time_label.text = "%s / %s" % [
				MidiStreamPlayer.format_time(position),
				MidiStreamPlayer.format_time(duration),
			]
		if _preview_control:
			_preview_control.queue_redraw()


# ─── 导出 JSON ────────────────────────────────────────────

func _on_export_json_pressed() -> void:
	if _current_object == null:
		return

	var res: MidiResource = _current_object
	var track_list: Array[TrackData] = []
	for track_res in res.tracks:
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

	if track_list.is_empty():
		push_warning("Clef: No MIDI data to export")
		return

	var midi_data := MidiData.new(
		res.tempo, track_list, res.timebase,
		res.tempo_events.duplicate(true),
		res.cc_events.duplicate(true),
		res.pitch_bend_events.duplicate(true),
		res.program_events.duplicate(true)
	)

	var json_text: String = MidiComposerConverter.to_json_string(midi_data)

	var dialog := EditorFileDialog.new()
	dialog.file_mode = EditorFileDialog.FILE_MODE_SAVE_FILE
	dialog.access = EditorFileDialog.ACCESS_RESOURCES
	dialog.title = l10n.t("Export JSON")
	dialog.filters = PackedStringArray([l10n.t("*.json ; JSON Files")])
	dialog.current_dir = _current_object.resource_path.get_base_dir()
	dialog.current_file = _current_object.resource_path.get_file().get_basename() + ".json"
	dialog.file_selected.connect(func(path: String) -> void:
		var file := FileAccess.open(path, FileAccess.WRITE)
		if file == null:
			push_error("Clef: Cannot write file %s" % path)
			return
		file.store_string(json_text)
		file.close()
		EditorInterface.get_resource_filesystem().scan()
		EditorInterface.get_base_control().remove_child(dialog)
		dialog.queue_free()
	)
	EditorInterface.get_base_control().add_child(dialog)
	dialog.popup_centered(Vector2i(800, 500))
