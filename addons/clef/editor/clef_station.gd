## Clef Station 主界面 — 三栏布局
## 左栏：音色浏览器 | 中栏：混音台 + 播放控制 | 右栏：MIDI 监视器
@tool
class_name ClefStation
extends Control

const SoundfontBrowser = preload("res://addons/clef/editor/soundfont_browser/soundfont_browser.gd")
const MidiMonitor = preload("res://addons/clef/editor/midi_monitor/midi_monitor.gd")
const EditorPlayer = preload("res://addons/clef/editor/editor_player/editor_player.gd")
const TransportBar = preload("res://addons/clef/editor/transport_bar/transport_bar.gd")
const MiniMixer = preload("res://addons/clef/editor/mini_mixer/mini_mixer.gd")
const PianoRoll = preload("res://addons/clef/editor/piano_roll/piano_roll.gd")

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
var _transport_bar: TransportBar
var _piano_roll: PianoRoll
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

	center_vbox.add_child(load_row)

	center_vbox.add_child(_transport_bar)

	_piano_roll = PianoRoll.new()
	_piano_roll.l10n = l10n
	_piano_roll.seek_requested.connect(func(pos: float):
		_editor_player.seek(pos)
	)
	center_vbox.add_child(_piano_roll)

	_mini_mixer = MiniMixer.new()
	_mini_mixer.l10n = l10n
	_mini_mixer.channel_mute_changed.connect(_piano_roll.set_channel_muted)
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
		push_warning("ClefStation: unsupported file format: %s" % path)
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
	dialog.filters = PackedStringArray(["*.mid ; MIDI", "*.tres ; MidiResource", "*.json ; JSON"])
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
	)
	_transport_bar.stop_pressed.connect(func():
		_editor_player.stop()
		_transport_bar.update_progress(0.0, _editor_player.get_duration())
		_progress_timer.stop()
	)
	_transport_bar.pause_pressed.connect(func():
		_editor_player.pause()
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
	# 提取每个通道的乐器（TrackResource.instrument）
	var channel_instruments: Dictionary = {}
	for track in midi_res.tracks:
		if not track.channel in channel_instruments:
			channel_instruments[track.channel] = track.instrument
	_piano_roll.set_channel_instruments(channel_instruments)
	_mini_mixer.clear_instruments()
	for ch in channel_instruments:
		_mini_mixer.set_channel_instrument(ch, channel_instruments[ch])


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
