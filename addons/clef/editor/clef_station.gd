## Clef Station 主界面 — 三栏布局
## 左栏：音色浏览器 | 中栏：混音台 + 播放控制 | 右栏：MIDI 监视器
@tool
class_name ClefStation
extends Control

var _left_panel: PanelContainer
var _center_panel: PanelContainer
var _right_panel: PanelContainer
var _split_main: HSplitContainer
var _btn_left: Button
var _btn_right: Button


func _init() -> void:
	custom_minimum_size = Vector2i(0, 0)


func _ready() -> void:
	# 填满父容器（编辑器主屏幕区域）
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_build_layout()


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
	var left_label := Label.new()
	left_label.text = "Soundfont Browser"
	left_label.add_theme_color_override("font_color", Color(0.7, 0.8, 1.0))
	_left_panel.add_child(left_label)
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
	var right_label := Label.new()
	right_label.text = "MIDI Monitor"
	right_label.add_theme_color_override("font_color", Color(1.0, 0.8, 0.7))
	_right_panel.add_child(right_label)
	split_right.add_child(_right_panel)


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
