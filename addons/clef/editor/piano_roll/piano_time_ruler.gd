## 时间刻度尺 — 与 PianoRoll 同步
@tool
class_name PianoTimeRuler
extends Control

## 点击刻度尺请求跳转
signal time_clicked(time: float)

## 拖拽刻度尺请求连续跳转
signal time_scrubbed(time: float)

const _BG_COLOR := Color(0.08, 0.08, 0.11)
const _TICK_COLOR := Color(0.35, 0.35, 0.4)
const _LABEL_COLOR := Color(0.5, 0.5, 0.55)
const _SCRUB_COLOR := Color(1.0, 0.85, 0.2)
const _PLAYBACK_COLOR := Color(0.95, 0.2, 0.2, 0.8)

var _view_offset: float = 0.0
var _zoom_level: float = 1.0
var _pixels_per_second: float = 100.0
var _duration: float = 0.0

var _scrubbing: bool = false
var _clicking: bool = false
var _hovered: bool = false
var _click_start_pos: Vector2 = Vector2.ZERO
var _playback_position: float = -1.0

const _DRAG_THRESHOLD: float = 3.0

var _hover_style: StyleBoxFlat = null


func _ready() -> void:
	custom_minimum_size = Vector2i(0, 24)
	mouse_default_cursor_shape = Control.CURSOR_ARROW
	_hover_style = StyleBoxFlat.new()
	_hover_style.bg_color = Color(0.0, 0.0, 0.0, 0.8)
	_hover_style.set_corner_radius_all(3)


## 由 PianoRoll 调用，同步缩放/滚动状态
func setup(view_offset: float, zoom_level: float, pps: float, dur: float) -> void:
	_view_offset = view_offset
	_zoom_level = zoom_level
	_pixels_per_second = pps
	_duration = dur
	queue_redraw()


## 由 ClefStation 调用，同步播放头位置
func set_playback_position(time: float) -> void:
	_playback_position = time
	queue_redraw()


func _effective_pps() -> float:
	return _pixels_per_second * _zoom_level


func _visible_time_range() -> float:
	var epps := _effective_pps()
	if epps <= 0.0: return _duration
	return float(size.x) / epps


func _screen_to_time(sx: float) -> float:
	var epps := _effective_pps()
	if epps <= 0.0: return 0.0
	return sx / epps + _view_offset


func _get_time_interval() -> float:
	var epps := _effective_pps()
	if epps <= 0.0: return 1.0
	var raw := 80.0 / epps  # ~80px between ticks
	var nice := [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0]
	for n in nice:
		if n >= raw:
			return n
	return 120.0


func _notification(what: int) -> void:
	if what == NOTIFICATION_MOUSE_ENTER:
		_hovered = true
		queue_redraw()
	elif what == NOTIFICATION_MOUSE_EXIT:
		_hovered = false
		_clicking = false
		_scrubbing = false
		queue_redraw()


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed:
			var t := _screen_to_time(mb.position.x)
			_clicking = true
			_click_start_pos = mb.position
			time_clicked.emit(t)
			get_viewport().set_input_as_handled()
		elif mb.button_index == MOUSE_BUTTON_LEFT and not mb.pressed:
			_clicking = false
			_scrubbing = false
			get_viewport().set_input_as_handled()
	if event is InputEventMouseMotion:
		if _clicking and not _scrubbing:
			var dist: float = event.position.distance_to(_click_start_pos)
			if dist > _DRAG_THRESHOLD:
				_scrubbing = true
		if _scrubbing:
			var t := _screen_to_time(event.position.x)
			time_scrubbed.emit(t)
		elif _hovered:
			queue_redraw()


func _draw() -> void:
	if _duration <= 0.0:
		draw_rect(Rect2(Vector2.ZERO, size), _BG_COLOR)
		return
	var rect := Rect2(Vector2.ZERO, size)
	# 背景
	draw_rect(rect, _BG_COLOR)
	# 底部分隔线
	var border_color := Color(0.25, 0.25, 0.3) if _hovered else Color(0.15, 0.15, 0.2)
	draw_line(Vector2(0, size.y - 1), Vector2(size.x, size.y - 1), border_color)

	var interval := _get_time_interval()
	if interval <= 0.0:
		return
	var start_t := floorf(_view_offset / interval) * interval
	var end_t := _view_offset + _visible_time_range()
	var t := start_t
	while t <= end_t:
		var x := _time_to_x(t)
		if x >= -50.0 and x <= size.x + 50.0:
			# 刻度线
			draw_line(Vector2(x, size.y - 6), Vector2(x, size.y), _TICK_COLOR)
		t += interval
	# 标签（每隔一个刻度显示，避免重叠）
	var label_interval := interval
	if _effective_pps() * interval < 40.0:
		label_interval = interval * 2.0
	var label_t := floorf(_view_offset / label_interval) * label_interval
	while label_t <= end_t:
		var x := _time_to_x(label_t)
		if x >= -50.0 and x <= size.x + 50.0:
			var label := "%.2fs" % label_t
			draw_string(
				ThemeDB.fallback_font,
				Vector2(x + 3, size.y - 6),
				label,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 11,
				_LABEL_COLOR
			)
		label_t += label_interval
	# 播放头指示线
	if _playback_position >= 0.0:
		var px := _time_to_x(_playback_position)
		if px >= 0.0 and px <= size.x:
			draw_line(Vector2(px, 0), Vector2(px, size.y), _PLAYBACK_COLOR, 2.0)
	# 悬停/点击/拖拽浮动标签
	if _hovered or _clicking or _scrubbing:
		_draw_hover_indicator()


func _draw_hover_indicator() -> void:
	var mouse_x := get_local_mouse_position().x
	if mouse_x < 0.0 or mouse_x > size.x:
		return
	var t := _screen_to_time(mouse_x)
	# 垂直指示线
	draw_line(Vector2(mouse_x, 0), Vector2(mouse_x, size.y), _SCRUB_COLOR)
	# 时间标签
	var time_text := "%.2fs" % t
	var font := ThemeDB.fallback_font
	var text_size := font.get_string_size(time_text)
	var pad := 4.0
	var label_w := text_size.x + pad * 2
	var label_h := text_size.y + pad * 2
	var label_x := mouse_x + 5.0
	var label_y := 2.0
	# 防越界：标签超出右边界时翻转到鼠标左侧
	if label_x + label_w > size.x:
		label_x = mouse_x - label_w - 5.0
	var label_bg := Rect2(label_x, label_y, label_w, label_h)
	draw_style_box(_hover_style, label_bg)
	draw_string(font, Vector2(label_x + pad, label_y + pad + text_size.y), time_text,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color.WHITE)


func _time_to_x(t: float) -> float:
	return (t - _view_offset) * _effective_pps()
