## 钢琴卷帘 — MIDI 音符可视化
@tool
class_name PianoRoll
extends Control

const ChannelColors = preload("res://addons/clef/editor/channel_colors.gd")

## 点击卷帘请求跳转到指定时间位置
signal seek_requested(position: float)

## 音符被修改（触发导出脏标记）
signal note_edited()

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


## 编辑命令（撤销/重做）
class EditCommand:
	var type: String          ## "move" | "resize" | "delete" | "add" | "property" | "mute" | "annotation"
	var description: String   ## 人类可读描述
	var before: Dictionary    ## 操作前状态快照
	var after: Dictionary     ## 操作后状态快照

	func _init(p_type: String = "", p_desc: String = "", p_before: Dictionary = {}, p_after: Dictionary = {}) -> void:
		type = p_type
		description = p_desc
		before = p_before
		after = p_after


## GM Level 1 乐器名称（128 个）
const _GM_NAMES: PackedStringArray = [
	"Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano",
	"Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet",
	"Celesta", "Glockenspiel", "Music Box", "Vibraphone",
	"Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
	"Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ",
	"Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
	"Nylon Guitar", "Steel Guitar", "Jazz Guitar", "Clean Guitar",
	"Muted Guitar", "Overdriven Guitar", "Distortion Guitar", "Guitar Harmonics",
	"Acoustic Bass", "Finger Bass", "Pick Bass", "Fretless Bass",
	"Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2",
	"Violin", "Viola", "Cello", "Contrabass",
	"Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
	"String Ensemble 1", "String Ensemble 2", "Synth Strings 1", "Synth Strings 2",
	"Choir Aahs", "Voice Oohs", "Synth Choir", "Orchestra Hit",
	"Trumpet", "Trombone", "Tuba", "Muted Trumpet",
	"French Horn", "Brass Section", "Synth Brass 1", "Synth Brass 2",
	"Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
	"Oboe", "English Horn", "Bassoon", "Clarinet",
	"Piccolo", "Flute", "Recorder", "Pan Flute",
	"Blown Bottle", "Shakuhachi", "Whistle", "Ocarina",
	"Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)", "Lead 4 (chiff)",
	"Lead 5 (charang)", "Lead 6 (voice)", "Lead 7 (fifths)", "Lead 8 (bass+lead)",
	"Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)", "Pad 4 (choir)",
	"Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)",
	"FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)",
	"FX 5 (brightness)", "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)",
	"Sitar", "Banjo", "Shamisen", "Koto",
	"Kalimba", "Bagpipe", "Fiddle", "Shanai",
	"Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
	"Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal",
	"Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
	"Telephone Ring", "Helicopter", "Applause", "Gunshot",
]

const _BG_COLOR := Color(0.06, 0.06, 0.09)
const _LEGEND_BG := Color(0.08, 0.08, 0.11)
const _GRID_LINE_COLOR := Color(0.12, 0.12, 0.16)
const _GRID_C_COLOR := Color(0.18, 0.18, 0.22)
const _PLAYBACK_COLOR := Color(1.0, 1.0, 1.0, 0.8)
const _LEGEND_HEIGHT: float = 28.0

var _notes: Array[RollNote] = []

## 撤销/重做栈
var _undo_stack: Array[EditCommand] = []
var _redo_stack: Array[EditCommand] = []
const MAX_HISTORY: int = 100

## 选中音符索引集合
var _selection: Array[int] = []

## 鼠标悬停音符索引（-1 表示无）
var _hovered_note: int = -1

var _duration: float = 0.0
var _playback_position: float = -1.0
var _min_pitch: int = 0
var _max_pitch: int = 127
var _pixels_per_second: float = 100.0
var _pixels_per_note: float = 10.0
var _active_channels: Array[int] = []
var _channel_instruments: Dictionary = {}  ## channel -> preset_index
var _muted_channels: Dictionary = {}      ## channel -> bool
var l10n: ClefL10n


func _ready() -> void:
	custom_minimum_size = Vector2i(0, 160)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	mouse_default_cursor_shape = Control.CURSOR_IBEAM


# ─── 公共 API ─────────────────────────────────────────────

## 设置音符数据并刷新
func set_notes(notes: Array[RollNote], duration: float) -> void:
	_notes = notes
	_undo_stack.clear()
	_redo_stack.clear()
	_selection.clear()
	_hovered_note = -1
	_duration = duration
	_collect_active_channels()
	_recalc_layout()
	queue_redraw()


## 设置通道乐器映射 (channel -> preset_index)
func set_channel_instruments(instruments: Dictionary) -> void:
	_channel_instruments = instruments
	queue_redraw()


## 设置通道静音状态（由 MiniMixer 触发）
func set_channel_muted(channel: int, muted: bool) -> void:
	if muted:
		_muted_channels[channel] = true
	else:
		_muted_channels.erase(channel)
	queue_redraw()


## 清除所有静音状态（加载新文件时调用）
func clear_muted_channels() -> void:
	_muted_channels.clear()
	queue_redraw()


## 更新播放头位置
func set_playback_position(position: float) -> void:
	_playback_position = position
	queue_redraw()


## 清空所有状态
func clear_notes() -> void:
	_notes.clear()
	_undo_stack.clear()
	_redo_stack.clear()
	_selection.clear()
	_hovered_note = -1
	_duration = 0.0
	_playback_position = -1.0
	_min_pitch = 0
	_max_pitch = 127
	_pixels_per_second = 100.0
	_pixels_per_note = 10.0
	_active_channels.clear()
	_channel_instruments.clear()
	_muted_channels.clear()
	queue_redraw()


# ─── 坐标映射 ─────────────────────────────────────────────

func _time_to_x(t: float) -> float:
	return t * _pixels_per_second


func _pixel_to_time(px: float) -> float:
	return px / _pixels_per_second


func _pitch_to_y(pitch: int) -> float:
	return _LEGEND_HEIGHT + (_max_pitch - pitch) * _pixels_per_note


func _y_to_pitch(py: float) -> int:
	return _max_pitch - int((py - _LEGEND_HEIGHT) / _pixels_per_note)


# ─── 布局计算 ─────────────────────────────────────────────

func _collect_active_channels() -> void:
	_active_channels.clear()
	var seen: Dictionary = {}
	for note in _notes:
		if not seen.has(note.channel):
			seen[note.channel] = true
			_active_channels.append(note.channel)
	_active_channels.sort()


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
	# 像素/音高：音域适配高度（减去图例高度）
	var h := float(size.y) - _LEGEND_HEIGHT
	var note_range := _max_pitch - _min_pitch + 1
	if h > 0.0 and note_range > 0:
		_pixels_per_note = h / float(note_range)


# ─── 生命周期 ─────────────────────────────────────────────

func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED:
		_recalc_layout()
		queue_redraw()


func _gui_input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key := event as InputEventKey
		if key.pressed:
			if key.ctrl_pressed and not key.shift_pressed and key.keycode == KEY_Z:
				get_viewport().set_input_as_handled()
				_undo()
				return
			if key.ctrl_pressed and key.shift_pressed and key.keycode == KEY_Z:
				get_viewport().set_input_as_handled()
				_redo()
				return
			if key.ctrl_pressed and key.keycode == KEY_Y:
				get_viewport().set_input_as_handled()
				_redo()
				return
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed:
			var hit := _hit_test(mb.position)
			if hit["index"] >= 0:
				if mb.ctrl_pressed:
					var idx: int = hit["index"]
					var found := _selection.find(idx)
					if found >= 0:
						_selection.remove_at(found)
					else:
						_selection.append(idx)
				else:
					_selection.clear()
					_selection.append(hit["index"])
				queue_redraw()
			else:
				_selection.clear()
				queue_redraw()
				var t := _pixel_to_time(mb.position.x)
				if _duration > 0.0 and t >= 0.0 and t <= _duration:
					seek_requested.emit(t)
		elif mb.button_index == MOUSE_BUTTON_LEFT and not mb.pressed:
			pass  # Phase 2: drag end
		elif mb.button_index == MOUSE_BUTTON_RIGHT:
			pass  # Phase 3: context menu

	if event is InputEventMouseMotion:
		var hit := _hit_test(event.position)
		if hit["index"] != _hovered_note:
			_hovered_note = hit["index"]
			queue_redraw()


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
			l10n.t("Load a MIDI file to view piano roll"),
			HORIZONTAL_ALIGNMENT_LEFT, -1, 14,
			Color(0.4, 0.4, 0.45)
		)
		return

	# 通道图例条
	_draw_legend()
	# 八度网格线
	_draw_pitch_grid()
	# 音符矩形
	_draw_notes()
	# 播放头
	_draw_playback_cursor()


func _draw_legend() -> void:
	# 图例背景
	draw_rect(Rect2(0, 0, size.x, _LEGEND_HEIGHT), _LEGEND_BG)
	# 底部分隔线
	draw_line(Vector2(0, _LEGEND_HEIGHT), Vector2(size.x, _LEGEND_HEIGHT), Color(0.2, 0.2, 0.25))
	# 各通道色块 + 标签（跳过静音通道）
	var x := 6.0
	var font := ThemeDB.fallback_font
	for ch in _active_channels:
		if _muted_channels.has(ch):
			continue
		var color: Color = ChannelColors.COLORS[ch % 16]
		# 色块 (20x20)
		draw_rect(Rect2(x, 4, 20, 20), color)
		x += 24.0
		# "ChN InstrumentName"
		var label := "Ch%d" % ch
		if ch == 9:
			label += " Standard Drum Kit"
		elif _channel_instruments.has(ch):
			var preset: int = _channel_instruments[ch]
			if preset >= 0 and preset < _GM_NAMES.size():
				label += " " + _GM_NAMES[preset]
		draw_string(
			font,
			Vector2(x, 20),
			label,
			HORIZONTAL_ALIGNMENT_LEFT, -1, 20,
			Color(0.6, 0.6, 0.65)
			)
		# 精确测量文字宽度
		var text_size := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 20)
		x += text_size.x + 16.0


func _draw_pitch_grid() -> void:
	for pitch in range(_min_pitch, _max_pitch + 1):
		var y := _pitch_to_y(pitch)
		var is_c := pitch % 12 == 0
		var color := _GRID_C_COLOR if is_c else _GRID_LINE_COLOR
		draw_line(Vector2(0, y), Vector2(size.x, y), color)


func _draw_notes() -> void:
	var sel_set: Dictionary = {}
	for idx in _selection:
		sel_set[idx] = true

	for i in _notes.size():
		var note := _notes[i]
		if _muted_channels.has(note.channel):
			continue
		var x := _time_to_x(note.start_time)
		var w := note.duration * _pixels_per_second
		if note.channel == 9:
			w = maxf(w, 2.0)
		var y := _pitch_to_y(note.pitch + 1)
		var h := _pixels_per_note - 1.0
		var base_color := ChannelColors.COLORS[note.channel % 16]
		var brightness := 0.5 + (float(note.velocity) / 127.0) * 0.5
		var color := Color(
			base_color.r * brightness,
			base_color.g * brightness,
			base_color.b * brightness
		)
		draw_rect(Rect2(x, y, w, h), color)

		# 选中高亮边框
		if sel_set.has(i):
			draw_rect(Rect2(x - 1, y - 1, w + 2, h + 2), Color(1, 1, 1, 0.9), false, 2.0)

		# 悬停高亮
		if i == _hovered_note:
			draw_rect(Rect2(x, y, w, h), Color(1, 1, 1, 0.15))


func _draw_playback_cursor() -> void:
	if _playback_position < 0.0 or _duration <= 0.0:
		return
	var x := _time_to_x(_playback_position)
	# 图例区域也画线
	draw_line(Vector2(x, 0), Vector2(x, size.y), _PLAYBACK_COLOR, 2.0)


# ─── 命中检测 ─────────────────────────────────────────────

## 返回 {index: int, edge: String}，edge: "none" | "left" | "right"
func _hit_test(pos: Vector2) -> Dictionary:
	var time := _pixel_to_time(pos.x)
	var pitch := _y_to_pitch(pos.y)
	for i in range(_notes.size() - 1, -1, -1):
		var n := _notes[i]
		if n.channel == 9 and _muted_channels.has(n.channel):
			continue
		if pitch == n.pitch and time >= n.start_time and time <= n.start_time + n.duration:
			var edge := _check_edge(pos, n)
			return {"index": i, "edge": edge}
	return {"index": -1, "edge": "none"}


func _check_edge(pos: Vector2, note: RollNote) -> String:
	var x_left := _time_to_x(note.start_time)
	var x_right := _time_to_x(note.start_time + note.duration)
	var tolerance := 4.0
	if absf(pos.x - x_left) <= tolerance:
		return "left"
	if absf(pos.x - x_right) <= tolerance:
		return "right"
	return "none"


# ─── 撤销/重做 ─────────────────────────────────────────────

func begin_command(type: String, description: String) -> EditCommand:
	return EditCommand.new(type, description)

func commit_command(cmd: EditCommand) -> void:
	_undo_stack.append(cmd)
	if _undo_stack.size() > MAX_HISTORY:
		_undo_stack.pop_front()
	_redo_stack.clear()
	_notify_edit()

func _undo() -> void:
	if _undo_stack.is_empty():
		return
	var cmd := _undo_stack.pop_back() as EditCommand
	_apply_snapshot(cmd.before)
	_redo_stack.append(cmd)
	_notify_edit()

func _redo() -> void:
	if _redo_stack.is_empty():
		return
	var cmd := _redo_stack.pop_back() as EditCommand
	_apply_snapshot(cmd.after)
	_undo_stack.append(cmd)
	_notify_edit()

func _notify_edit() -> void:
	queue_redraw()
	note_edited.emit()

## 深拷贝 RollNote，防止 undo 栈引用被修改
func _clone_note(n: RollNote) -> RollNote:
	return RollNote.new(n.channel, n.pitch, n.start_time, n.duration, n.velocity)

func _apply_snapshot(snapshot: Dictionary) -> void:
	if snapshot.has("deleted_note"):
		_notes.insert(snapshot["index"], snapshot["deleted_note"])
	elif snapshot.has("added_index"):
		_notes.remove_at(snapshot["added_index"])
	elif snapshot.has("index") and snapshot.has("note_data"):
		var idx: int = snapshot["index"]
		if idx >= 0 and idx < _notes.size():
			_notes[idx] = snapshot["note_data"]
		else:
			push_warning("Undo/redo: snapshot index %d out of bounds (size %d)" % [idx, _notes.size()])
