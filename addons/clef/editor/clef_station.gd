## Clef Station 主界面 — 三栏布局
## 左栏：音色浏览器 | 中栏：混音台 + 播放控制 | 右栏：MIDI 监视器
@tool
class_name ClefStation
extends Control


const _CONFIG_PATH = "user://clef_editor.cfg"
const SUPPORTED_EXTENSIONS: PackedStringArray = [".mid", ".tres", ".json"]

var _left_panel: PanelContainer
var _center_panel: PanelContainer
var _right_panel: PanelContainer
var _split_main: HSplitContainer
var _split_right: HSplitContainer
var _btn_left: Button
var _btn_right: Button
var _soundfont_browser: SoundfontBrowser
var _bridge: RefCounted = null
var _midi_monitor: MidiMonitor
var _editor_player: EditorPlayer
var _edit_dirty: bool = false
var _mode_buttons: Array[Button] = []
var _transport_bar: TransportBar
var _piano_roll: PianoRoll
var _velocity_lane: VelocityLane
var _velocity_toggle: Button
var _mini_mixer: MiniMixer
var _progress_timer: Timer = null
var _last_midi_dir: String = ""
var _last_midi_file: String = ""
var _auto_load: bool = false
var _left_visible: bool = true
var _right_visible: bool = true
var _saved_split_main_offset: int = 220
var _saved_split_right_offset: int = -200
var l10n: ClefL10n


func _init() -> void:
	custom_minimum_size = Vector2i(0, 0)


func _ready() -> void:
	# 填满父容器（编辑器主屏幕区域）
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_load_editor_config()
	_build_layout()
	_apply_saved_layout()
	_load_soundfont_profile()
	_init_editor_player()
	_init_progress_timer()
	# 自动加载上次文件
	if _auto_load and _last_midi_file != "" and FileAccess.file_exists(_last_midi_file):
		_load_midi_file(_last_midi_file)


func _build_layout() -> void:
	var root := VBoxContainer.new()
	root.name = "Root"
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(root)

	# ── 工具栏 ──
	var toolbar := HBoxContainer.new()
	toolbar.name = "Toolbar"
	toolbar.add_theme_constant_override("separation", 8)
	toolbar.custom_minimum_size = Vector2i(0, 32)
	root.add_child(toolbar)

	_btn_left = Button.new()
	_btn_left.text = l10n.t("SF2 Browser")
	_btn_left.toggle_mode = true
	_btn_left.button_pressed = _left_visible
	_btn_left.tooltip_text = l10n.t("Toggle Soundfont Browser panel")
	_btn_left.toggled.connect(set_left_panel_visible)
	toolbar.add_child(_btn_left)

	_btn_right = Button.new()
	_btn_right.text = l10n.t("MIDI Monitor")
	_btn_right.toggle_mode = true
	_btn_right.button_pressed = _right_visible
	_btn_right.tooltip_text = l10n.t("Toggle MIDI Monitor panel")
	_btn_right.toggled.connect(set_right_panel_visible)
	toolbar.add_child(_btn_right)

	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	toolbar.add_child(spacer)

	# ── 三栏分割 ──
	_split_main = HSplitContainer.new()
	_split_main.name = "SplitMain"
	_split_main.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_split_main.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_split_main.split_offset = _saved_split_main_offset
	_split_main.dragged.connect(_on_split_dragged)
	root.add_child(_split_main)

	# 左栏：音色浏览器
	_left_panel = PanelContainer.new()
	_left_panel.name = "LeftPanel"
	_left_panel.custom_minimum_size = Vector2i(180, 0)
	_left_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_style_panel(_left_panel, Color(0.12, 0.12, 0.16))
	_soundfont_browser = SoundfontBrowser.new()
	_soundfont_browser.l10n = l10n
	_soundfont_browser.patch_selected.connect(_on_patch_selected)
	_left_panel.add_child(_soundfont_browser)
	_split_main.add_child(_left_panel)

	# 中右分割
	_split_right = HSplitContainer.new()
	_split_right.name = "SplitRight"
	_split_right.split_offset = _saved_split_right_offset
	_split_right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_split_right.dragged.connect(_on_split_dragged)
	_split_main.add_child(_split_right)

	# 中栏：传输控制 + 钢琴卷帘 + 混音台
	_center_panel = PanelContainer.new()
	_center_panel.name = "CenterPanel"
	_center_panel.custom_minimum_size = Vector2i(200, 0)
	_center_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_center_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_style_panel(_center_panel, Color(0.10, 0.10, 0.14))
	var center_vbox := VBoxContainer.new()
	center_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	center_vbox.size_flags_vertical = Control.SIZE_EXPAND_FILL
	center_vbox.add_theme_constant_override("separation", 4)

	_transport_bar = TransportBar.new()
	_transport_bar.l10n = l10n

	# 加载按钮行
	var load_row := HBoxContainer.new()
	load_row.add_theme_constant_override("separation", 6)
	var load_btn := Button.new()
	load_btn.text = l10n.t("Load MIDI")
	load_btn.tooltip_text = l10n.t("Load .mid / .tres / .json file")
	load_btn.pressed.connect(_on_load_pressed)
	load_row.add_child(load_btn)

	var auto_load_btn := Button.new()
	auto_load_btn.text = l10n.t("Auto")
	auto_load_btn.custom_minimum_size = Vector2i(36, 0)
	auto_load_btn.toggle_mode = true
	auto_load_btn.button_pressed = _auto_load
	auto_load_btn.tooltip_text = l10n.t("Auto-load last file on startup")
	_set_toggle_style(auto_load_btn, _auto_load, Color(0.5, 0.8, 0.5))
	auto_load_btn.toggled.connect(func(pressed: bool):
		_auto_load = pressed
		_set_toggle_style(auto_load_btn, pressed, Color(0.5, 0.8, 0.5))
		_save_editor_config()
	)
	load_row.add_child(auto_load_btn)
	# 模式切换按钮
	var mode_spacer := Control.new()
	mode_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	load_row.add_child(mode_spacer)
	var mode_group := ButtonGroup.new()
	var btn_play := Button.new()
	btn_play.text = l10n.t("▶ Playback mode")
	btn_play.toggle_mode = true
	btn_play.button_group = mode_group
	btn_play.button_pressed = true
	btn_play.pressed.connect(func():
		_piano_roll.set_mode(PianoRoll.Mode.PLAYBACK)
		_editor_player.stop()
		_progress_timer.stop()
		_transport_bar.update_progress(0.0, _editor_player.get_duration())
	)
	load_row.add_child(btn_play)
	var btn_edit := Button.new()
	btn_edit.text = l10n.t("✏ Edit mode")
	btn_edit.toggle_mode = true
	btn_edit.button_group = mode_group
	btn_edit.pressed.connect(func():
		_piano_roll.set_mode(PianoRoll.Mode.EDIT)
		_editor_player.stop()
		_progress_timer.stop()
		_transport_bar.update_progress(0.0, _editor_player.get_duration())
	)
	load_row.add_child(btn_edit)
	var btn_feedback := Button.new()
	btn_feedback.text = l10n.t("❗ Feedback mode")
	btn_feedback.toggle_mode = true
	btn_feedback.button_group = mode_group
	btn_feedback.pressed.connect(func():
		_piano_roll.set_mode(PianoRoll.Mode.FEEDBACK)
	)
	load_row.add_child(btn_feedback)
	_mode_buttons = [btn_play, btn_edit, btn_feedback]
	_update_mode_button_highlight(PianoRoll.Mode.PLAYBACK)

	center_vbox.add_child(load_row)

	center_vbox.add_child(_transport_bar)

	_piano_roll = PianoRoll.new()
	_piano_roll.l10n = l10n
	_piano_roll.set_soundfont_browser(_soundfont_browser)
	_piano_roll.seek_requested.connect(func(pos: float):
		_editor_player.seek(pos)
	)
	_piano_roll.export_requested.connect(_on_piano_roll_export)
	_piano_roll.note_edited.connect(_on_piano_roll_note_edited)
	_piano_roll.track_changed.connect(_on_track_changed)
	_piano_roll.agent_feedback_requested.connect(func(feedback: Dictionary, fpath: String = ""):
		var abs_path: String
		if fpath != "":
			abs_path = fpath
		else:
			var timestamp := Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "_")
			abs_path = ProjectSettings.globalize_path("res://addons/clef/output/agent_feedback_" + timestamp + ".json")
		DirAccess.make_dir_recursive_absolute(abs_path.get_base_dir())
		var file := FileAccess.open(abs_path, FileAccess.WRITE)
		if file:
			file.store_string(JSON.stringify(feedback, "\t"))
			file.close()
			print("[ClefStation] Agent feedback exported: ", abs_path)
			EditorInterface.get_resource_filesystem().scan()
		else:
			push_error("[ClefStation] Failed to export agent feedback: ", abs_path)
	)
	_piano_roll.abc_export_requested.connect(func():
		# Trigger MIDI export first, then convert to ABC
		_on_piano_roll_export(_piano_roll.get_notes())
		# Find the most recently exported MIDI file
		var dir := DirAccess.open("res://addons/clef/output/")
		if dir:
			dir.list_dir_begin()
			var latest_midi := ""
			var latest_time := 0
			var file_name := dir.get_next()
			while file_name != "":
				if file_name.begins_with("edited_") and file_name.ends_with(".mid"):
					var full_path := "res://addons/clef/output/" + file_name
					var modified: int = FileAccess.get_modified_time(ProjectSettings.globalize_path(full_path))
					if modified > latest_time:
						latest_time = modified
						latest_midi = full_path
				file_name = dir.get_next()
			dir.list_dir_end()
			if latest_midi.is_empty():
				push_warning("[ClefStation] No edited MIDI found for ABC export")
				return
			var timestamp := Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "_")
			var abc_path := "res://addons/clef/output/edited_" + timestamp + ".abc"
			var abs_midi := ProjectSettings.globalize_path(latest_midi)
			var abs_abc := ProjectSettings.globalize_path(abc_path)
			var script_path := ProjectSettings.globalize_path("res://.claude/skills/clef-compose/scripts/clef_tools.py")
			var output := []
			OS.execute("python", [script_path, "midi-to-abc", abs_midi, "-o", abs_abc], output)
			print("[ClefStation] ABC export triggered: ", abs_abc)
		else:
			push_warning("[ClefStation] Cannot open output directory for ABC export")
	)

	# 时间刻度尺
	var _piano_ruler: PianoTimeRuler = PianoTimeRuler.new()
	_piano_ruler.time_clicked.connect(func(t: float): _editor_player.seek(t); _piano_roll.set_playback_position(t, true))
	_piano_ruler.time_scrubbed.connect(func(t: float): _editor_player.seek(t); _piano_roll.set_playback_position(t, true))
	_piano_roll.view_offset_changed.connect(_piano_ruler.setup)
	_piano_roll.playback_position_changed.connect(_piano_ruler.set_playback_position)
	center_vbox.add_child(_piano_ruler)

	_piano_roll.size_flags_stretch_ratio = 2
	center_vbox.add_child(_piano_roll)

	# ── Velocity Lane ──
	_velocity_lane = VelocityLane.new()
	_velocity_lane.custom_minimum_size = Vector2i(0, 80)
	_velocity_lane.size_flags_stretch_ratio = 1
	_velocity_lane.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_velocity_lane.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	_velocity_toggle = Button.new()
	_velocity_toggle.text = "▼ " + l10n.t("Velocity")
	_velocity_toggle.flat = true
	_velocity_toggle.custom_minimum_size = Vector2i(0, 24)
	_velocity_toggle.pressed.connect(func() -> void:
			_velocity_lane.visible = not _velocity_lane.visible
			_velocity_toggle.text = ("▼ " if _velocity_lane.visible else "▶ ") + l10n.t("Velocity")
	)
	center_vbox.add_child(_velocity_toggle)
	center_vbox.add_child(_velocity_lane)

	# PianoRoll → VelocityLane 信号连接
	_piano_roll.selection_changed.connect(_velocity_lane.set_selection)
	_piano_roll.note_edited.connect(func() -> void:
			_velocity_lane.set_notes(_piano_roll.get_notes())
	)
	_piano_roll.track_changed.connect(func(ch: int, _preset: int) -> void:
			_velocity_lane.set_active_channel(ch)
	)
	_velocity_lane.note_hovered.connect(func(idx: int) -> void:
			_piano_roll.set_hovered_note(idx)
	)
	_piano_roll.mode_changed.connect(func(mode: int) -> void:
			_velocity_lane.set_edit_mode(mode)
	)
	_piano_roll.view_offset_changed.connect(func(vo: float, zl: float, pps: float, dur: float) -> void:
			_velocity_lane.update_view(vo, zl, pps, dur)
	)

	# VelocityLane → PianoRoll: 通知 velocity 变更
	_velocity_lane.velocity_changed.connect(func(note_index: int, new_velocity: int) -> void:
			_on_velocity_changed(note_index, new_velocity)
	)

	_mini_mixer = MiniMixer.new()
	_mini_mixer.l10n = l10n
	_mini_mixer.channel_mute_changed.connect(_piano_roll.set_channel_muted)
	_mini_mixer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	center_vbox.add_child(_mini_mixer)

	_center_panel.add_child(center_vbox)
	_split_right.add_child(_center_panel)

	# 右栏：MIDI 监视器
	_right_panel = PanelContainer.new()
	_right_panel.name = "RightPanel"
	_right_panel.custom_minimum_size = Vector2i(180, 0)
	_right_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_style_panel(_right_panel, Color(0.14, 0.10, 0.10))
	_midi_monitor = MidiMonitor.new()
	_midi_monitor.l10n = l10n
	_right_panel.add_child(_midi_monitor)
	_split_right.add_child(_right_panel)

	# 延迟连接 bridge
	if _bridge != null:
		if _midi_monitor != null:
			_midi_monitor.connect_bridge(_bridge)


func _set_toggle_style(btn: Button, active: bool, accent: Color) -> void:
	var style := StyleBoxFlat.new()
	if active:
		style.bg_color = Color(accent.r * 0.25, accent.g * 0.25, accent.b * 0.25)
		btn.add_theme_color_override("font_color", accent)
	else:
		style.bg_color = Color(0.18, 0.18, 0.20)
		btn.add_theme_color_override("font_color", Color(0.45, 0.45, 0.45))
	style.set_content_margin_all(4)
	style.set_corner_radius_all(3)
	btn.add_theme_stylebox_override("normal", style)


func _style_panel(panel: PanelContainer, bg_color: Color) -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = bg_color
	style.set_content_margin_all(8)
	style.set_corner_radius_all(0)
	panel.add_theme_stylebox_override("panel", style)


func _is_supported_file(path: String) -> bool:
	for ext in SUPPORTED_EXTENSIONS:
		if path.ends_with(ext):
			return true
	return false


func set_left_panel_visible(visible: bool) -> void:
	_left_visible = visible
	_left_panel.visible = visible
	_save_editor_config()


func set_right_panel_visible(visible: bool) -> void:
	_right_visible = visible
	_right_panel.visible = visible
	_save_editor_config()


func set_bridge(bridge: RefCounted) -> void:
	_bridge = bridge
	if _midi_monitor != null:
		_midi_monitor.connect_bridge(_bridge)
	if _editor_player != null:
		_editor_player.setup(self, _bridge)
	if _mini_mixer != null:
		_bridge.midi_program_change.connect(_mini_mixer.set_channel_instrument)


func _init_editor_player() -> void:
	_editor_player = EditorPlayer.new()
	_editor_player.l10n = l10n
	_editor_player.setup(self, _bridge)
	_editor_player.file_loaded.connect(func(_path: String, _dur: float):
		_update_piano_roll()
	)
	_wire_transport()
	_wire_mixer()
	_piano_roll.mode_changed.connect(_update_mode_button_highlight)


func _init_progress_timer() -> void:
	_progress_timer = Timer.new()
	_progress_timer.wait_time = 0.05
	_progress_timer.timeout.connect(_update_progress)
	add_child(_progress_timer)


func _can_drop_data(at_position: Vector2, data: Variant) -> bool:
	if data is Dictionary and data.has("type") and data["type"] == "files":
		var files: Array = data.get("files", [])
		for f in files:
			if _is_supported_file(f):
				return true
	return false


func _drop_data(at_position: Vector2, data: Variant) -> void:
	if not _can_drop_data(at_position, data):
		return
	var files: Array = data.get("files", [])
	for f in files:
		if _is_supported_file(f):
			_load_midi_file(f)
			break


func _load_midi_file(path: String) -> void:
	if not _is_supported_file(path):
		push_warning("ClefStation: unsupported file format: %s" % path)  # Debug-only, not localized
		return
	_last_midi_file = path
	_last_midi_dir = path.get_base_dir()
	_save_editor_config()
	_editor_player.load_file(path)
	_transport_bar.set_file_name(path.get_file())


func _on_load_pressed() -> void:
	var dialog := EditorFileDialog.new()
	dialog.file_mode = EditorFileDialog.FILE_MODE_OPEN_FILE
	dialog.access = EditorFileDialog.ACCESS_RESOURCES
	dialog.title = l10n.t("Load MIDI")
	dialog.filters = PackedStringArray([l10n.t("*.mid ; MIDI"), l10n.t("*.tres ; MidiResource"), l10n.t("*.json ; JSON")])
	if _last_midi_dir != "":
		dialog.current_dir = _last_midi_dir
	EditorInterface.get_base_control().add_child(dialog)
	dialog.canceled.connect(func():
		EditorInterface.get_base_control().remove_child(dialog)
		dialog.queue_free()
	)
	dialog.file_selected.connect(func(path: String):
		_load_midi_file(path)
		EditorInterface.get_base_control().remove_child(dialog)
		dialog.queue_free()
	)
	dialog.popup_centered(Vector2i(800, 600))


func _wire_transport() -> void:
	_transport_bar.play_pressed.connect(func():
		if _editor_player.is_playing():
			return
		_editor_player.play()
		_progress_timer.start()
		_piano_roll.set_playing(true)
	)
	_transport_bar.stop_pressed.connect(func():
		_editor_player.stop()
		_transport_bar.update_progress(0.0, _editor_player.get_duration())
		_progress_timer.stop()
		_piano_roll.set_playing(false)
		_piano_roll.set_playback_position(0.0, true)
	)
	_transport_bar.pause_pressed.connect(func():
		_editor_player.pause()
		_piano_roll.set_playing(false)
	)
	_transport_bar.seek_requested.connect(func(pos: float):
		_editor_player.seek(pos)
	)


func _wire_mixer() -> void:
	_mini_mixer.master_volume_changed.connect(func(vol: float):
		_editor_player.set_master_volume(vol)
	)
	_mini_mixer.channel_volume_changed.connect(func(ch: int, vol: float):
		_editor_player.set_channel_volume(ch, vol)
	)
	_mini_mixer.channel_mute_changed.connect(func(ch: int, muted: bool):
		_editor_player.set_channel_mute(ch, muted)
	)
	_editor_player.set_master_volume(_mini_mixer.get_master_volume())
	for ch in MiniMixer.CHANNEL_COUNT:
		_editor_player.set_channel_volume(ch, _mini_mixer.get_channel_volume(ch))
		_editor_player.set_channel_mute(ch, _mini_mixer.is_channel_muted(ch))


func _update_mode_button_highlight(active_mode: int) -> void:
	var accent := Color(0.3, 0.6, 1.0)
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.15, 0.15, 0.18)
	normal.set_border_width_all(1)
	normal.border_color = Color(0.3, 0.3, 0.35)
	normal.set_corner_radius_all(4)
	var active := StyleBoxFlat.new()
	active.bg_color = Color(0.2, 0.25, 0.35)
	active.set_border_width_all(2)
	active.border_color = accent
	active.set_corner_radius_all(4)
	for i in _mode_buttons.size():
		if i == active_mode:
			_mode_buttons[i].add_theme_stylebox_override("normal", active)
			_mode_buttons[i].add_theme_stylebox_override("hover", active)
			_mode_buttons[i].add_theme_stylebox_override("pressed", active)
		else:
			_mode_buttons[i].add_theme_stylebox_override("normal", normal)
			_mode_buttons[i].add_theme_stylebox_override("hover", normal)
			_mode_buttons[i].add_theme_stylebox_override("pressed", normal)



func _update_progress() -> void:
	if _editor_player.is_playing() or _editor_player.is_paused():
		_transport_bar.update_progress(
			_editor_player.get_position(),
			_editor_player.get_duration()
		)
		_piano_roll.set_playback_position(_editor_player.get_position())
	# 检测播放结束（不在播放/暂停状态且有已加载文件）
	if not _editor_player.is_playing() and not _editor_player.is_paused() and _editor_player.get_duration() > 0:
		if _transport_bar.is_looping():
			_editor_player.play()
		else:
			_progress_timer.stop()
			_transport_bar.update_progress(0.0, _editor_player.get_duration())
			_piano_roll.set_playback_position(0.0)


func _update_piano_roll() -> void:
	var midi_res: MidiResource = _editor_player.get_midi_resource()
	if midi_res == null or midi_res.tracks.is_empty():
		_piano_roll.clear_notes()
		_piano_roll.clear_muted_channels()
		return
	var roll_notes: Array[PianoRoll.RollNote] = []
	var ticks_per_second: float = float(midi_res.tempo) / 60.0 * float(midi_res.timebase)
	if ticks_per_second <= 0.0:
		return
	for track in midi_res.tracks:
		for note in track.notes:
			var start_time: float = float(note.start_ticks) / ticks_per_second
			var duration: float = float(note.duration_ticks) / ticks_per_second
			roll_notes.append(PianoRoll.RollNote.new(
				track.channel, note.pitch, start_time, duration, note.velocity
			))
	var duration: float = _editor_player.get_duration()
	_piano_roll.set_notes(roll_notes, duration)
	_velocity_lane.set_notes(_piano_roll.get_notes())
	# 提取每个通道的乐器（TrackResource.instrument）
	var channel_instruments: Dictionary = {}
	for track in midi_res.tracks:
		if not track.channel in channel_instruments:
			channel_instruments[track.channel] = track.instrument
	_piano_roll.set_channel_instruments(channel_instruments)
	_mini_mixer.clear_instruments()
	for ch in channel_instruments:
		_mini_mixer.set_channel_instrument(ch, channel_instruments[ch])



func _build_midi_data_from_notes(notes: Array) -> MidiData:
	var midi_res: MidiResource = _editor_player.get_midi_resource()
	if midi_res == null:
		return null
	var midi_data := MidiData.new(
		midi_res.tempo, [], midi_res.timebase,
		midi_res.tempo_events.duplicate(true),
		midi_res.cc_events.duplicate(true),
		midi_res.pitch_bend_events.duplicate(true),
		midi_res.program_events.duplicate(true)
	)
	var channel_notes: Dictionary = {}
	var ticks_per_second := float(midi_res.tempo) / 60.0 * float(midi_res.timebase)
	if ticks_per_second <= 0.0:
		return null
	for idx in range(notes.size()):
		if _piano_roll.is_note_muted(idx):
			continue
		var rn = notes[idx]
		var ch: int = rn.channel
		if ch == 9 and _piano_roll.is_channel_muted(ch):
			continue
		if not channel_notes.has(ch):
			channel_notes[ch] = []
		var start_ticks := int(rn.start_time * ticks_per_second)
		var duration_ticks := int(rn.duration * ticks_per_second)
		channel_notes[ch].append(NoteData.new(rn.pitch, start_ticks, duration_ticks, rn.velocity))

	# 获取 Piano Roll 中用户设置的通道乐器映射
	var roll_instruments: Dictionary = _piano_roll.get_channel_instruments()
	# 收集原始 MIDI 中已有 program_events 的通道
	var existing_channels: Dictionary = {}
	for pc in midi_data.program_events:
		existing_channels[int(pc["channel"])] = true

	for ch in channel_notes:
		var track := TrackData.new()
		track.channel = ch
		track.notes.assign(channel_notes[ch])
		for orig_track in midi_res.tracks:
			if orig_track.channel == ch:
				track.instrument = orig_track.instrument
				track.name = orig_track.name
				break
		# 用户在 Piano Roll 中为该通道指定了新音色
		if roll_instruments.has(ch):
			var preset: int = int(roll_instruments[ch])
			track.instrument = preset
			if not existing_channels.has(ch):
				midi_data.program_events.append({
					"time_ticks": 0,
					"channel": ch,
					"preset_index": preset,
				})
			else:
				for pc in midi_data.program_events:
					if int(pc["channel"]) == ch:
						pc["preset_index"] = preset
						break
			midi_data.tracks.append(track)
	return midi_data

func _on_piano_roll_note_edited() -> void:
	_edit_dirty = true
	call_deferred("_flush_edit_sync")

func _on_track_changed(channel: int, preset: int) -> void:
	_mini_mixer.set_channel_instrument(channel, preset)
	_edit_dirty = true
	call_deferred("_flush_edit_sync")

func _on_velocity_changed(note_index: int, new_velocity: int) -> void:
	_piano_roll.set_note_velocity(note_index, new_velocity)

func _flush_edit_sync() -> void:
	if not _edit_dirty:
		return
	_edit_dirty = false
	var midi_data := _build_midi_data_from_notes(_piano_roll.get_notes())
	if midi_data == null:
		return
	var new_res := MidiResource.new()
	new_res.from_midi_data(midi_data)
	_editor_player.update_resource(new_res)
func _on_piano_roll_export(notes: Array, fpath: String = "") -> void:
	var midi_data := _build_midi_data_from_notes(notes)
	if midi_data == null:
		return
	# Write file
	var bytes := MidiWriter.encode(midi_data)
	var abs_path: String
	if fpath != "":
		abs_path = fpath
	else:
		var output_dir := "res://addons/clef/output/"
		var timestamp := Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "_")
		abs_path = ProjectSettings.globalize_path(output_dir + "edited_" + timestamp + ".mid")
	# Ensure directory exists
	DirAccess.make_dir_recursive_absolute(abs_path.get_base_dir())
	var file := FileAccess.open(abs_path, FileAccess.WRITE)
	if file:
		file.store_buffer(bytes)
		file.close()
		print("[ClefStation] MIDI exported: ", abs_path)
		EditorInterface.get_resource_filesystem().scan()
	else:
		push_error("[ClefStation] Failed to export MIDI: ", abs_path)


func _on_patch_selected(preset_index: int, patch: PatchData) -> void:
	pass


func _load_soundfont_profile() -> void:
	var sf2_path: String = ProjectSettings.get_setting("clef/default_soundfont", "")
	if sf2_path == "":
		return
	if not FileAccess.file_exists(sf2_path):
		return
	var sf2_dir: String = sf2_path.get_base_dir()
	var sf2_name: String = sf2_path.get_file().get_basename()
	var profile_path: String = sf2_dir.path_join(sf2_name + "_profile.json")

	# Fallback 1: plugin-bundled profile in knowledge/
	if not FileAccess.file_exists(profile_path):
		var knowledge_name := "sf2_" + sf2_name.to_lower().replace(" ", "_") + ".json"
		var knowledge_path := "res://addons/clef/knowledge/" + knowledge_name
		if FileAccess.file_exists(knowledge_path):
			profile_path = knowledge_path

	# Fallback 2: plugin-bundled profile in sound_front/
	if not FileAccess.file_exists(profile_path):
		var bundled_path := "res://addons/clef/sound_front/" + sf2_name + "_profile.json"
		if FileAccess.file_exists(bundled_path):
			profile_path = bundled_path

	# Fallback 3: generate via Python profiler
	if not FileAccess.file_exists(profile_path):
		var profiler := ProjectSettings.globalize_path("res://.claude/skills/clef-compose/scripts/sf2_profiler.py")
		var global_sf2 := ProjectSettings.globalize_path(sf2_path)
		var global_profile := ProjectSettings.globalize_path(profile_path)
		var output := []
		OS.execute("python", [profiler, global_sf2, "-o", global_profile], output)

	if FileAccess.file_exists(profile_path):
		_soundfont_browser.load_profile(profile_path)
		_soundfont_browser.setup_audition(sf2_path)


# ─── 布局持久化 ────────────────────────────────────────

func _apply_saved_layout() -> void:
	_split_main.split_offset = _saved_split_main_offset
	_split_right.split_offset = _saved_split_right_offset
	_left_panel.visible = _left_visible
	_right_panel.visible = _right_visible
	_btn_left.button_pressed = _left_visible
	_btn_right.button_pressed = _right_visible


func _on_split_dragged(_offset: int) -> void:
	_save_editor_config()


func _load_editor_config() -> void:
	var config := ConfigFile.new()
	if config.load(_CONFIG_PATH) == OK:
		_last_midi_dir = config.get_value("editor", "last_midi_dir", "")
		_last_midi_file = config.get_value("editor", "last_midi_file", "")
		_auto_load = config.get_value("editor", "auto_load", false)
		_left_visible = config.get_value("layout", "left_visible", true)
		_right_visible = config.get_value("layout", "right_visible", true)
		_saved_split_main_offset = clamp(config.get_value("layout", "split_main_offset", 220), -2000, 2000)
		_saved_split_right_offset = clamp(config.get_value("layout", "split_right_offset", -200), -2000, 2000)


func _save_editor_config() -> void:
	var config := ConfigFile.new()
	config.load(_CONFIG_PATH)  # 保留其他 section（如 midi_monitor）
	config.set_value("editor", "last_midi_dir", _last_midi_dir)
	config.set_value("editor", "last_midi_file", _last_midi_file)
	config.set_value("editor", "auto_load", _auto_load)
	config.set_value("layout", "split_main_offset", _split_main.split_offset)
	config.set_value("layout", "split_right_offset", _split_right.split_offset)
	config.set_value("layout", "left_visible", _left_visible)
	config.set_value("layout", "right_visible", _right_visible)
	config.save(_CONFIG_PATH)
