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
var l10n: ClefL10n


func _can_handle(object: Object) -> bool:
	return object is MidiResource


func _parse_end(object: Object) -> void:
	# Release old UI containers to prevent node leaks
	if _container:
		_container.queue_free()
		_container = null
	if _export_container:
		_export_container.queue_free()
		_export_container = null

	# Stop previous playback if switching objects
	if object != _current_object and _player != null:
		_stop_playback()
	_current_object = object as MidiResource

	if not _current_object:
		return

	# Soundfont source
	var sf2_path: String = ProjectSettings.get_setting(
		"clef/default_soundfont", "")
	if sf2_path == "":
		sf2_path = _current_object.preview_soundfont if _current_object.has_method("get") else ""

	_container = HBoxContainer.new()

	# Play button
	_play_button = Button.new()
	_play_button.text = "▶ " + l10n.t("Play")
	_play_button.tooltip_text = l10n.t("Preview MIDI playback")
	_play_button.disabled = sf2_path == ""
	_play_button.pressed.connect(_on_play_pressed)
	_container.add_child(_play_button)

	# Stop button
	_stop_button = Button.new()
	_stop_button.text = "⏹ " + l10n.t("Stop")
	_stop_button.tooltip_text = l10n.t("Stop")
	_stop_button.disabled = true
	_stop_button.pressed.connect(_on_stop_pressed)
	_container.add_child(_stop_button)

	# Pause button
	_pause_button = Button.new()
	_pause_button.text = "⏸"
	_pause_button.tooltip_text = l10n.t("Pause")
	_pause_button.disabled = true
	_pause_button.pressed.connect(_on_pause_pressed)
	_container.add_child(_pause_button)

	# Progress slider (supports seek)
	_progress_slider = HSlider.new()
	_progress_slider.custom_minimum_size.x = 150
	_progress_slider.max_value = 1.0
	_progress_slider.value = 0.0
	_progress_slider.step = 0.01
	_progress_slider.min_value = 0.0
	_progress_slider.drag_ended.connect(_on_slider_drag_ended)
	_container.add_child(_progress_slider)

	# Time label
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

	# Export JSON button (second row)
	_export_container = HBoxContainer.new()

	_export_button = Button.new()
	_export_button.text = l10n.t("Export JSON")
	_export_button.tooltip_text = l10n.t("Export MIDI resource to Clef JSON v2.0 format (for LLM composition)")
	_export_button.pressed.connect(_on_export_json_pressed)
	_export_container.add_child(_export_button)

	add_custom_control(_export_container)


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

	# Progress polling
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


func _on_export_json_pressed() -> void:
	if _current_object == null:
		return

	var res: MidiResource = _current_object

	# Build MidiData directly from @export properties to avoid calling script methods on placeholders
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
