## Clef Station 主界面 — 三栏布局
## 左栏：音色浏览器 | 中栏：混音台 + 播放控制 | 右栏：MIDI 监视器
@tool
class_name ClefStation
extends Control

const SoundfontBrowser = preload("res://addons/clef/editor/soundfont_browser/soundfont_browser.gd")
const MidiMonitor = preload("res://addons/clef/editor/midi_monitor/midi_monitor.gd")

var _left_panel: PanelContainer
var _center_panel: PanelContainer
var _right_panel: PanelContainer
var _split_main: HSplitContainer
var _btn_left: Button
var _btn_right: Button
var _soundfont_browser: SoundfontBrowser
var _bridge: RefCounted = null
var _midi_monitor: MidiMonitor


func _init() -> void:
	custom_minimum_size = Vector2i(0, 0)


func _ready() -> void:
	# 填满父容器（编辑器主屏幕区域）
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_build_layout()
	_load_soundfont_profile()


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
	_btn_left.text = "SF2 Browser"
	_btn_left.toggle_mode = true
	_btn_left.button_pressed = true
	_btn_left.tooltip_text = "Toggle Soundfont Browser panel"
	_btn_left.toggled.connect(set_left_panel_visible)
	toolbar.add_child(_btn_left)

	_btn_right = Button.new()
	_btn_right.text = "MIDI Monitor"
	_btn_right.toggle_mode = true
	_btn_right.button_pressed = true
	_btn_right.tooltip_text = "Toggle MIDI Monitor panel"
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
	_split_main.split_offset = 220
	root.add_child(_split_main)

	# 左栏：音色浏览器
	_left_panel = PanelContainer.new()
	_left_panel.name = "LeftPanel"
	_left_panel.custom_minimum_size = Vector2i(180, 0)
	_left_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_style_panel(_left_panel, Color(0.12, 0.12, 0.16))
	_soundfont_browser = SoundfontBrowser.new()
	_soundfont_browser.patch_selected.connect(_on_patch_selected)
	_left_panel.add_child(_soundfont_browser)
	_split_main.add_child(_left_panel)

	# 中右分割
	var split_right := HSplitContainer.new()
	split_right.name = "SplitRight"
	split_right.split_offset = -200
	split_right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_split_main.add_child(split_right)

	# 中栏：混音台
	_center_panel = PanelContainer.new()
	_center_panel.name = "CenterPanel"
	_center_panel.custom_minimum_size = Vector2i(200, 0)
	_center_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_center_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_style_panel(_center_panel, Color(0.10, 0.10, 0.14))
	var center_label := Label.new()
	center_label.text = "Mixer & Transport"
	center_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	center_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	center_label.size_flags_vertical = Control.SIZE_EXPAND_FILL
	center_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	center_label.add_theme_color_override("font_color", Color(0.7, 1.0, 0.7))
	_center_panel.add_child(center_label)
	split_right.add_child(_center_panel)

	# 右栏：MIDI 监视器
	_right_panel = PanelContainer.new()
	_right_panel.name = "RightPanel"
	_right_panel.custom_minimum_size = Vector2i(180, 0)
	_right_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_style_panel(_right_panel, Color(0.14, 0.10, 0.10))
	_midi_monitor = MidiMonitor.new()
	_right_panel.add_child(_midi_monitor)
	split_right.add_child(_right_panel)

	# 延迟连接 bridge（可能早于 _ready 设置）
	if _bridge != null and _midi_monitor != null:
		_midi_monitor.connect_bridge(_bridge)


func _style_panel(panel: PanelContainer, bg_color: Color) -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = bg_color
	style.set_content_margin_all(8)
	style.set_corner_radius_all(0)
	panel.add_theme_stylebox_override("panel", style)


func set_left_panel_visible(visible: bool) -> void:
	_left_panel.visible = visible


func set_right_panel_visible(visible: bool) -> void:
	_right_panel.visible = visible


func set_bridge(bridge: RefCounted) -> void:
	_bridge = bridge
	if _midi_monitor != null:
		_midi_monitor.connect_bridge(_bridge)


func _on_patch_selected(preset_index: int, patch: PatchData) -> void:
	# Phase 3 将联动混音台，当前仅打印日志
	print("[ClefStation] Patch selected: %03d %s" % [preset_index, patch.name])


func _load_soundfont_profile() -> void:
	var sf2_path: String = ProjectSettings.get_setting("clef/default_soundfont", "")
	if sf2_path == "":
		return
	if not FileAccess.file_exists(sf2_path):
		return
	# 确定同目录下的 profile JSON 路径
	var sf2_dir: String = sf2_path.get_base_dir()
	var sf2_name: String = sf2_path.get_file().get_basename()
	var profile_path: String = sf2_dir.path_join(sf2_name + "_profile.json")
	# 自动生成 profile（如果不存在）
	if not FileAccess.file_exists(profile_path):
		var profiler := ProjectSettings.globalize_path("res://.claude/skills/clef-compose/scripts/sf2_profiler.py")
		var global_sf2 := ProjectSettings.globalize_path(sf2_path)
		var global_profile := ProjectSettings.globalize_path(profile_path)
		var output := []
		OS.execute("python", [profiler, global_sf2, "-o", global_profile], output)
	if FileAccess.file_exists(profile_path):
		_soundfont_browser.load_profile(profile_path)
		_soundfont_browser.setup_audition(sf2_path)
