## 迷你混音台 — 16 通道音量滑块 + 静音 + 主音量
@tool
class_name MiniMixer
extends VBoxContainer

signal channel_volume_changed(channel: int, volume_db: float)
signal channel_mute_changed(channel: int, muted: bool)
signal master_volume_changed(volume_db: float)

const CHANNEL_COUNT: int = 16

var _channel_sliders: Array[VSlider] = []
var _mute_buttons: Array[Button] = []
var _master_slider: HSlider
var _master_label: Label


func _ready() -> void:
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_build_ui()


func _channel_panel_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.12, 0.12, 0.14)
	style.set_border_width_all(1)
	style.set_border_color(Color(0.25, 0.25, 0.28))
	style.set_content_margin_all(3)
	style.set_corner_radius_all(2)
	return style


func _build_ui() -> void:
	var channels_row := HBoxContainer.new()
	channels_row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	channels_row.size_flags_vertical = Control.SIZE_EXPAND_FILL
	channels_row.add_theme_constant_override("separation", 2)

	for i in range(CHANNEL_COUNT):
		var panel := PanelContainer.new()
		panel.add_theme_stylebox_override("panel", _channel_panel_style())

		var strip := VBoxContainer.new()
		strip.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		strip.add_theme_constant_override("separation", 1)

		var lbl := Label.new()
		lbl.text = "Ch%d" % i
		lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		lbl.add_theme_font_size_override("font_size", 9)
		lbl.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
		strip.add_child(lbl)

		var slider := VSlider.new()
		slider.min_value = 0.0
		slider.max_value = 1.0
		slider.step = 0.01
		slider.value = 1.0
		slider.size_flags_vertical = Control.SIZE_EXPAND_FILL
		slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		slider.custom_minimum_size = Vector2i(16, 60)
		slider.tooltip_text = "Channel %d volume" % i
		slider.drag_ended.connect(_on_channel_slider_ended.bind(i))
		strip.add_child(slider)
		_channel_sliders.append(slider)

		var mute_btn := Button.new()
		mute_btn.text = "M"
		mute_btn.custom_minimum_size = Vector2i(0, 16)
		mute_btn.toggle_mode = true
		mute_btn.add_theme_font_size_override("font_size", 9)
		mute_btn.tooltip_text = "Mute Channel %d" % i
		_set_mute_style(mute_btn, false)
		mute_btn.toggled.connect(_on_mute_toggled.bind(i, mute_btn))
		strip.add_child(mute_btn)
		_mute_buttons.append(mute_btn)

		panel.add_child(strip)
		channels_row.add_child(panel)

	add_child(channels_row)

	# 主音量行
	var master_row := HBoxContainer.new()
	master_row.add_theme_constant_override("separation", 6)

	var master_title := Label.new()
	master_title.text = "Master"
	master_title.custom_minimum_size = Vector2i(40, 0)
	master_title.add_theme_color_override("font_color", Color(0.9, 0.9, 0.7))
	master_row.add_child(master_title)

	_master_slider = HSlider.new()
	_master_slider.min_value = -60.0
	_master_slider.max_value = 6.0
	_master_slider.step = 1.0
	_master_slider.value = -12.0
	_master_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_master_slider.tooltip_text = "Master volume"
	_master_slider.value_changed.connect(_on_master_slider_changed)
	master_row.add_child(_master_slider)

	_master_label = Label.new()
	_master_label.text = "-12 dB"
	_master_label.custom_minimum_size = Vector2i(48, 0)
	_master_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	master_row.add_child(_master_label)

	add_child(master_row)


func _set_mute_style(btn: Button, muted: bool) -> void:
	var style := StyleBoxFlat.new()
	if muted:
		style.bg_color = Color(0.35, 0.15, 0.15)
		btn.add_theme_color_override("font_color", Color(1.0, 0.4, 0.4))
	else:
		style.bg_color = Color(0.18, 0.18, 0.20)
		btn.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	style.set_content_margin_all(3)
	style.set_corner_radius_all(2)
	btn.add_theme_stylebox_override("normal", style)


func _on_channel_slider_ended(value_changed: bool, channel: int) -> void:
	channel_volume_changed.emit(channel, _channel_sliders[channel].value)


func _on_master_slider_changed(value: float) -> void:
	_master_label.text = "%.0f dB" % value
	master_volume_changed.emit(value)


func _on_mute_toggled(pressed: bool, channel: int, btn: Button) -> void:
	_set_mute_style(btn, pressed)
	_channel_sliders[channel].editable = not pressed
	channel_mute_changed.emit(channel, pressed)
