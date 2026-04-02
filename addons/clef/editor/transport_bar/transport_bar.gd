## 传输控制栏 — 播放/停止/暂停 + 进度条 + 时间显示
@tool
class_name TransportBar
extends HBoxContainer

signal play_pressed
signal stop_pressed
signal pause_pressed
signal seek_requested(position: float)

var _btn_play: Button
var _btn_stop: Button
var _btn_pause: Button
var _progress_slider: HSlider
var _time_label: Label
var _file_label: Label
var _loop_btn: Button
var _loop: bool = false
var _seeking: bool = false

var l10n: ClefL10n

func _ready() -> void:
	custom_minimum_size = Vector2i(0, 32)
	add_theme_constant_override("separation", 6)
	_build_ui()


func _build_ui() -> void:
	_file_label = Label.new()
	_file_label.text = l10n.t("No file loaded")
	_file_label.custom_minimum_size = Vector2i(120, 0)
	_file_label.clip_text = true
	_file_label.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
	add_child(_file_label)

	_btn_play = Button.new()
	_btn_play.text = l10n.t("Play")
	_btn_play.custom_minimum_size = Vector2i(40, 0)
	_btn_play.tooltip_text = l10n.t("Play")
	_btn_play.pressed.connect(play_pressed.emit)
	add_child(_btn_play)

	_btn_pause = Button.new()
	_btn_pause.text = l10n.t("Pause")
	_btn_pause.custom_minimum_size = Vector2i(40, 0)
	_btn_pause.tooltip_text = l10n.t("Pause")
	_btn_pause.pressed.connect(pause_pressed.emit)
	add_child(_btn_pause)

	_btn_stop = Button.new()
	_btn_stop.text = l10n.t("Stop")
	_btn_stop.custom_minimum_size = Vector2i(40, 0)
	_btn_stop.tooltip_text = l10n.t("Stop")
	_btn_stop.pressed.connect(stop_pressed.emit)
	add_child(_btn_stop)

	_loop_btn = Button.new()
	_loop_btn.text = l10n.t("Loop")
	_loop_btn.custom_minimum_size = Vector2i(36, 0)
	_loop_btn.toggle_mode = true
	_loop_btn.tooltip_text = l10n.t("Loop")
	_set_loop_style(false)
	_loop_btn.toggled.connect(func(pressed: bool):
		_set_loop_style(pressed)
		_loop = pressed
	)
	add_child(_loop_btn)

	_progress_slider = HSlider.new()
	_progress_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_progress_slider.min_value = 0.0
	_progress_slider.max_value = 100.0
	_progress_slider.step = 0.1
	_progress_slider.value = 0.0
	_progress_slider.custom_minimum_size = Vector2i(100, 0)
	_progress_slider.drag_started.connect(func(): _seeking = true)
	_progress_slider.drag_ended.connect(func(_val: bool):
		_seeking = false
		seek_requested.emit(_progress_slider.value)
	)
	add_child(_progress_slider)

	_time_label = Label.new()
	_time_label.text = "00:00 / 00:00"
	_time_label.custom_minimum_size = Vector2i(90, 0)
	_time_label.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
	add_child(_time_label)


func set_file_name(name: String) -> void:
	_file_label.text = name


func update_progress(position: float, duration: float) -> void:
	if _seeking:
		return
	if duration > 0:
		_progress_slider.max_value = duration
	_progress_slider.value = position
	_time_label.text = "%s / %s" % [_format_time(position), _format_time(duration)]


func _set_loop_style(active: bool) -> void:
	var style := StyleBoxFlat.new()
	if active:
		style.bg_color = Color(0.35, 0.30, 0.10)
		_loop_btn.add_theme_color_override("font_color", Color(1.0, 0.85, 0.3))
	else:
		style.bg_color = Color(0.18, 0.18, 0.20)
		_loop_btn.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	style.set_content_margin_all(4)
	style.set_corner_radius_all(3)
	_loop_btn.add_theme_stylebox_override("normal", style)


func _format_time(seconds: float) -> String:
	var m := int(seconds) / 60
	var s := int(seconds) % 60
	return "%02d:%02d" % [m, s]


func is_looping() -> bool:
	return _loop
