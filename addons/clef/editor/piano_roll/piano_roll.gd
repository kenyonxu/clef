## 钢琴卷帘 — MIDI 音符可视化
@tool
class_name PianoRoll
extends Control

## 点击卷帘请求跳转到指定时间位置
signal seek_requested(position: float)

## 单条音符数据
class RollNote:
	var channel: int
	var pitch: int
	var start_time: float  ## 秒
	var duration: float    ## 秒
	var velocity: int      ## 0-127

	func _init(ch: int = 0, p: int = 60, start: float = 0.0, dur: float = 0.0, vel: int = 100) -> void:
		channel = ch
		pitch = p
		start_time = start
		duration = dur
		velocity = vel


## 16 通道颜色（各色相、中等饱和度）
const _CHANNEL_COLORS: Array[Color] = [
	Color(0.85, 0.45, 0.45),  # Ch 0  红
	Color(0.45, 0.80, 0.45),  # Ch 1  绿
	Color(0.45, 0.60, 0.90),  # Ch 2  蓝
	Color(0.90, 0.80, 0.40),  # Ch 3  黄
	Color(0.80, 0.50, 0.85),  # Ch 4  紫
	Color(0.45, 0.85, 0.80),  # Ch 5  青
	Color(0.90, 0.60, 0.40),  # Ch 6  橙
	Color(0.70, 0.70, 0.80),  # Ch 7  灰蓝
	Color(0.85, 0.55, 0.70),  # Ch 8  粉
	Color(0.60, 0.75, 0.55),  # Ch 9  鼓绿
	Color(0.55, 0.55, 0.90),  # Ch 10 靛蓝
	Color(0.90, 0.70, 0.55),  # Ch 11 桃
	Color(0.50, 0.80, 0.70),  # Ch 12 薄荷
	Color(0.80, 0.65, 0.85),  # Ch 13 薰衣草
	Color(0.75, 0.85, 0.45),  # Ch 14 黄绿
	Color(0.85, 0.80, 0.75),  # Ch 15 米色
]

const _BG_COLOR := Color(0.06, 0.06, 0.09)
const _GRID_LINE_COLOR := Color(0.12, 0.12, 0.16)
const _GRID_C_COLOR := Color(0.18, 0.18, 0.22)
const _PLAYBACK_COLOR := Color(1.0, 1.0, 1.0, 0.8)

var _notes: Array[RollNote] = []
var _duration: float = 0.0
var _playback_position: float = -1.0
var _min_pitch: int = 0
var _max_pitch: int = 127
var _pixels_per_second: float = 100.0
var _pixels_per_note: float = 10.0


func _ready() -> void:
	custom_minimum_size = Vector2i(0, 160)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	mouse_default_cursor_shape = Control.CURSOR_IBEAM


# ─── 公共 API ─────────────────────────────────────────────

## 设置音符数据并刷新
func set_notes(notes: Array[RollNote], duration: float) -> void:
	_notes = notes
	_duration = duration
	_recalc_layout()
	queue_redraw()


## 更新播放头位置
func set_playback_position(position: float) -> void:
	_playback_position = position
	queue_redraw()


## 清空所有状态
func clear_notes() -> void:
	_notes.clear()
	_duration = 0.0
	_playback_position = -1.0
	_min_pitch = 0
	_max_pitch = 127
	_pixels_per_second = 100.0
	_pixels_per_note = 10.0
	queue_redraw()


# ─── 坐标映射 ─────────────────────────────────────────────

func _time_to_x(t: float) -> float:
	return t * _pixels_per_second


func _pixel_to_time(px: float) -> float:
	return px / _pixels_per_second


func _pitch_to_y(pitch: int) -> float:
	return (_max_pitch - pitch) * _pixels_per_note


func _y_to_pitch(py: float) -> int:
	return _max_pitch - int(py / _pixels_per_note)


# ─── 布局计算 ─────────────────────────────────────────────

func _recalc_layout() -> void:
	if _notes.is_empty():
		return
	# 计算音域范围
	var lo: int = 127
	var hi: int = 0
	for note in _notes:
		lo = mini(lo, note.pitch)
		hi = maxi(hi, note.pitch)
	# 加 ±1 八度边距
	_min_pitch = maxi(0, lo - 12)
	_max_pitch = mini(127, hi + 12)
	# 像素/秒：整首歌适配宽度
	var w := float(size.x)
	if w > 0.0 and _duration > 0.0:
		_pixels_per_second = w / _duration
	# 像素/音高：音域适配高度
	var h := float(size.y)
	var note_range := _max_pitch - _min_pitch + 1
	if h > 0.0 and note_range > 0:
		_pixels_per_note = h / float(note_range)


# ─── 生命周期 ─────────────────────────────────────────────

func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED:
		_recalc_layout()
		queue_redraw()


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed:
			var t := _pixel_to_time(mb.position.x)
			if _duration > 0.0 and t >= 0.0 and t <= _duration:
				seek_requested.emit(t)


# ─── 绘制 ─────────────────────────────────────────────────

func _draw() -> void:
	var rect := Rect2(Vector2.ZERO, size)
	# 背景
	draw_rect(rect, _BG_COLOR)

	if _notes.is_empty():
		# 占位文本
		draw_string(
			ThemeDB.fallback_font,
			Vector2(16, size.y / 2.0 + 8),
			"Load a MIDI file to view piano roll",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 14,
			Color(0.4, 0.4, 0.45)
		)
		return

	# 八度网格线
	_draw_pitch_grid()
	# 音符矩形
	_draw_notes()
	# 播放头
	_draw_playback_cursor()


func _draw_pitch_grid() -> void:
	for pitch in range(_min_pitch, _max_pitch + 1):
		var y := _pitch_to_y(pitch)
		var is_c := pitch % 12 == 0
		var color := _GRID_C_COLOR if is_c else _GRID_LINE_COLOR
		draw_line(Vector2(0, y), Vector2(size.x, y), color)


func _draw_notes() -> void:
	for note in _notes:
		var x := _time_to_x(note.start_time)
		var w := note.duration * _pixels_per_second
		# 鼓声（channel 9）最小 2px 宽
		if note.channel == 9:
			w = maxf(w, 2.0)
		var y := _pitch_to_y(note.pitch + 1)  # +1 因为 pitch_to_y 是顶部
		var h := _pixels_per_note - 1.0
		# 通道颜色 * 力度亮度
		var base_color := _CHANNEL_COLORS[note.channel % 16]
		var brightness := 0.5 + (float(note.velocity) / 127.0) * 0.5
		var color := Color(
			base_color.r * brightness,
			base_color.g * brightness,
			base_color.b * brightness
		)
		draw_rect(Rect2(x, y, w, h), color)


func _draw_playback_cursor() -> void:
	if _playback_position < 0.0 or _duration <= 0.0:
		return
	var x := _time_to_x(_playback_position)
	draw_line(Vector2(x, 0), Vector2(x, size.y), _PLAYBACK_COLOR, 2.0)
