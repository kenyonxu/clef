## 钢琴卷帘 — MIDI 音符可视化
@tool
class_name PianoRoll
extends Control

const ChannelColors = preload("res://addons/clef/editor/channel_colors.gd")

## 点击卷帘请求跳转到指定时间位置
signal seek_requested(position: float)

## 音符被修改（触发导出脏标记）
signal note_edited()

## 请求导出 MIDI
signal export_requested(notes: Array)

## 添加标注
signal annotation_added(note_index: int, text: String, severity: String)

## 请求导出 Agent 反馈 JSON
signal agent_feedback_requested(feedback: Dictionary)

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


## 审查标注
class Annotation:
	var note_index: int
	var text: String
	var severity: String  ## "info" | "warning" | "error"

	func _init(p_idx: int = 0, p_text: String = "", p_sev: String = "info") -> void:
		note_index = p_idx
		text = p_text
		severity = p_sev


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

## 拖拽状态
var _dragging: bool = false
var _drag_type: int = 0  ## 0=NONE, 1=MOVE, 2=RESIZE_LEFT, 3=RESIZE_RIGHT
var _drag_start_pos: Vector2 = Vector2.ZERO
var _drag_original_notes: Array[Dictionary] = []  ## 拖拽前快照 [{index, pitch, start_time, duration}]

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

var _context_menu: PopupMenu = null
var _velocity_dialog: AcceptDialog = null

var _annotations: Array[Annotation] = []
var _annotation_popup: PanelContainer = null

## 屏蔽（逐音符静音）索引
var _muted_indices: Array[int] = []


func _ready() -> void:
	custom_minimum_size = Vector2i(0, 160)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	mouse_default_cursor_shape = Control.CURSOR_IBEAM
	_create_context_menu()


# ─── 公共 API ─────────────────────────────────────────────

## 设置音符数据并刷新
func set_notes(notes: Array[RollNote], duration: float) -> void:
	_notes = notes
	_undo_stack.clear()
	_redo_stack.clear()
	_selection.clear()
	_annotations.clear()
	_muted_indices.clear()
	_hovered_note = -1
	_duration = duration
	_collect_active_channels()
	_recalc_layout()
	queue_redraw()


## 获取当前音符数组
func get_notes() -> Array[RollNote]:
	return _notes## 设置通道乐器映射 (channel -> preset_index)
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
	_annotations.clear()
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
	_muted_indices.clear()
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
			if key.keycode == KEY_DELETE and not _selection.is_empty():
				get_viewport().set_input_as_handled()
				_delete_selected()
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
				# 开始拖拽
				_dragging = true
				_drag_start_pos = mb.position
				_drag_original_notes.clear()
				if hit["edge"] == "left":
					_drag_type = 2
				elif hit["edge"] == "right":
					_drag_type = 3
				else:
					_drag_type = 1  # MOVE
				for idx in _selection:
					var n := _notes[idx]
					_drag_original_notes.append({
						"index": idx,
						"pitch": n.pitch,
						"start_time": n.start_time,
						"duration": n.duration,
					})
				queue_redraw()
			else:
				_selection.clear()
				queue_redraw()
				var t := _pixel_to_time(mb.position.x)
				if _duration > 0.0 and t >= 0.0 and t <= _duration:
					seek_requested.emit(t)
			elif mb.button_index == MOUSE_BUTTON_LEFT and not mb.pressed and _dragging:
				_dragging = false
				var changed := false
				for orig in _drag_original_notes:
					var idx: int = orig["index"]
					if idx >= 0 and idx < _notes.size():
						var n := _notes[idx]
						if n.pitch != orig["pitch"] or n.start_time != orig["start_time"] or n.duration != orig["duration"]:
							changed = true
							break
				if changed:
					var cmd_type := "move" if _drag_type == 1 else "resize"
					var cmd := begin_command(cmd_type, "拖拽编辑音符")
					cmd.before = {"indices": _drag_original_notes.duplicate(true)}
					var after_snap := []
					for orig in _drag_original_notes:
						var idx: int = orig["index"]
						if idx >= 0 and idx < _notes.size():
							after_snap.append({
								"index": idx,
								"pitch": _notes[idx].pitch,
								"start_time": _notes[idx].start_time,
								"duration": _notes[idx].duration,
							})
					cmd.after = {"indices": after_snap}
					commit_command(cmd)
				_drag_type = 0
				_drag_original_notes.clear()
			elif mb.button_index == MOUSE_BUTTON_LEFT and not mb.pressed:
				pass
			elif mb.button_index == MOUSE_BUTTON_RIGHT and mb.pressed:
				var hit := _hit_test(mb.position)
				if hit["index"] >= 0:
					if not _selection.has(hit["index"]):
						_selection.clear()
						_selection.append(hit["index"])
						queue_redraw()
					_context_menu.position = get_global_mouse_position() + Vector2(2, 2)
					_context_menu.popup()
					get_viewport().set_input_as_handled()

	if event is InputEventMouseMotion:
		if _dragging:
			var delta := event.position - _drag_start_pos
			match _drag_type:
				1:  # MOVE
					var pitch_delta := int(delta.y / _pixels_per_note)
					var time_delta := delta.x / _pixels_per_second
					for orig in _drag_original_notes:
						var idx: int = orig["index"]
						if idx >= 0 and idx < _notes.size():
							_notes[idx].pitch = orig["pitch"] - pitch_delta
							_notes[idx].start_time = orig["start_time"] + time_delta
					queue_redraw()
				2:  # RESIZE_LEFT
					var time_delta := delta.x / _pixels_per_second
					for orig in _drag_original_notes:
						var idx: int = orig["index"]
						if idx >= 0 and idx < _notes.size():
							_notes[idx].start_time = orig["start_time"] + time_delta
							_notes[idx].duration = orig["duration"] - time_delta
					queue_redraw()
				3:  # RESIZE_RIGHT
					var time_delta := delta.x / _pixels_per_second
					for orig in _drag_original_notes:
						var idx: int = orig["index"]
						if idx >= 0 and idx < _notes.size():
							_notes[idx].duration = orig["duration"] + time_delta
					queue_redraw()
		else:
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
	_draw_annotations()


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
			# 屏蔽态：半透明 + 删除线
			if _is_note_muted(i):
				color.a = 0.3
				draw_rect(Rect2(x, y, w, h), color)
				draw_line(Vector2(x, y + h / 2), Vector2(x + w, y + h / 2), Color(1, 0.3, 0.3), 1.5)
				# Still show selection border if selected
				if sel_set.has(i):
					draw_rect(Rect2(x - 1, y - 1, w + 2, h + 2), Color(1, 1, 1, 0.5), false, 2.0)
				continue
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


# ─── 编辑操作 ─────────────────────────────────────────────

func _delete_selected() -> void:
	if _selection.is_empty():
		return
	var sorted := _selection.duplicate()
	sorted.sort_custom(func(a, b): return a > b)

	var cmd := begin_command("delete", "删除 %d 个音符" % sorted.size())
	var deleted_items := []
	for idx in sorted:
		deleted_items.append({"index": idx, "note_data": _clone_note(_notes[idx])})
	cmd.before = {"deleted_items": deleted_items}

	for idx in sorted:
		_notes.remove_at(idx)

	cmd.after = {"deleted_indices": sorted.duplicate()}
	_selection.clear()
	commit_command(cmd)


func _draw_annotations() -> void:
	var colors := {
		"info": Color(0.3, 0.7, 1.0),
		"warning": Color(1.0, 0.8, 0.2),
		"error": Color(1.0, 0.3, 0.3),
	}
	var drawn_count: Dictionary = {}
	for ann in _annotations:
		if ann.note_index < 0 or ann.note_index >= _notes.size():
			continue
		var note := _notes[ann.note_index]
		var x := _time_to_x(note.start_time)
		var y := _pitch_to_y(note.pitch + 1)
		var offset := drawn_count.get(ann.note_index, 0)
		drawn_count[ann.note_index] = offset + 1
		var color: Color = colors.get(ann.severity, colors["info"])
		var tri_x := x + offset * 8.0
		var tri_size := 6.0
		var points := PackedVector2Array([
			Vector2(tri_x, y - 2),
			Vector2(tri_x + tri_size, y - 2),
			Vector2(tri_x + tri_size / 2, y - tri_size - 2),
		])
		draw_colored_polygon(points, color)



func _get_agent_feedback() -> Dictionary:
	var annotations_data := []
	for ann in _annotations:
		if ann.note_index < 0 or ann.note_index >= _notes.size():
			continue
		var note := _notes[ann.note_index]
		annotations_data.append({
			"channel": note.channel,
			"pitch": note.pitch,
			"severity": ann.severity,
			"note": ann.text,
		})
	return {
		"version": 1,
		"annotations": annotations_data,
	}


func _toggle_mute_selected() -> void:
	if _selection.is_empty():
		return
	var newly_muted := []
	var newly_unmuted := []
	for idx in _selection:
		var found := _muted_indices.find(idx)
		if found >= 0:
			_muted_indices.remove_at(found)
			newly_unmuted.append(idx)
		else:
			_muted_indices.append(idx)
			newly_muted.append(idx)
	if not newly_muted.is_empty() or not newly_unmuted.is_empty():
		var cmd := begin_command("mute", "屏蔽 %d / 恢复 %d" % [newly_muted.size(), newly_unmuted.size()])
		cmd.before = {"muted_indices": newly_unmuted.duplicate()}
		cmd.after = {"muted_indices": newly_muted.duplicate()}
		commit_command(cmd)
	queue_redraw()


func _is_note_muted(index: int) -> bool:
	return _muted_indices.find(index) >= 0

func _create_context_menu() -> void:
	_context_menu = PopupMenu.new()
	_context_menu.id_pressed.connect(_on_context_menu_item)
	add_child(_context_menu)
	_context_menu.add_item("删除音符", 0)
	_context_menu.add_item("音高 +1", 1)
	_context_menu.add_item("音高 -1", 2)
	_context_menu.add_separator()
	_context_menu.add_item("编辑力度...", 3)
	_context_menu.add_separator()
	_context_menu.add_item("添加标注...", 4)
	_context_menu.add_item("屏蔽（临时静音）", 5)
	_context_menu.add_separator()
	_context_menu.add_item("导出修改后的 MIDI", 10)
	_context_menu.add_item("生成 Agent 反馈", 11)


func _on_context_menu_item(id: int) -> void:
	match id:
		0:
			_delete_selected()
		1:
			_shift_selected_pitch(1)
		2:
			_shift_selected_pitch(-1)
		3:
			_edit_velocity_popup()
		10:
			export_requested.emit(_notes)
		4:
			_open_annotation_popup()
			5:
				_toggle_mute_selected()
			11:
				agent_feedback_requested.emit(_get_agent_feedback())


func _shift_selected_pitch(delta: int) -> void:
	if _selection.is_empty():
		return
	var cmd := begin_command("property", "音高 %+d" % delta)
	var before_snap := []
	var after_snap := []
	for idx in _selection:
		if idx >= 0 and idx < _notes.size():
			before_snap.append({"index": idx, "pitch": _notes[idx].pitch})
			_notes[idx].pitch = clampi(_notes[idx].pitch + delta, 0, 127)
			after_snap.append({"index": idx, "pitch": _notes[idx].pitch})
	cmd.before = {"pitch_changes": before_snap}
	cmd.after = {"pitch_changes": after_snap}
	commit_command(cmd)


func _edit_velocity_popup() -> void:
	if _selection.is_empty():
		return
	_velocity_dialog = AcceptDialog.new()
	_velocity_dialog.title = "编辑力度"
	var vbox := VBoxContainer.new()
	var label := Label.new()
	label.text = "力度 (0-127):"
	vbox.add_child(label)
	var input := LineEdit.new()
	input.placeholder_text = "100"
	if not _selection.is_empty():
		var first_note: RollNote = _notes[_selection[0]]
		input.text = str(first_note.velocity)
	input.alignment = HORIZONTAL_ALIGNMENT_CENTER
	vbox.add_child(input)
	_velocity_dialog.add_child(vbox)
	_velocity_dialog.confirmed.connect(func():
		var val := int(input.text)
		if val >= 0 and val <= 127:
			_set_selected_velocity(val)
		_velocity_dialog.queue_free()
	)
	add_child(_velocity_dialog)
	_velocity_dialog.popup_centered(Vector2i(200, 100))
	input.grab_focus()
	input.select_all()


func _set_selected_velocity(vel: int) -> void:
	var cmd := begin_command("property", "力度 → %d" % vel)
	var before_snap := []
	var after_snap := []
	for idx in _selection:
		if idx >= 0 and idx < _notes.size():
			before_snap.append({"index": idx, "velocity": _notes[idx].velocity})
			_notes[idx].velocity = vel
			after_snap.append({"index": idx, "velocity": vel})
	cmd.before = {"velocity_changes": before_snap}
	cmd.after = {"velocity_changes": after_snap}
	commit_command(cmd)



func _open_annotation_popup() -> void:
	if _selection.is_empty():
		return
	if _annotation_popup == null:
		_create_annotation_popup()
	_annotation_popup.position = get_global_mouse_position() + Vector2(5, 5)
	_annotation_popup.visible = true


func _create_annotation_popup() -> void:
	_annotation_popup = PanelContainer.new()
	var vbox := VBoxContainer.new()
	var sev_hbox := HBoxContainer.new()
	var sev_label := Label.new()
	sev_label.text = "严重度:"
	sev_hbox.add_child(sev_label)
	var sev_option := OptionButton.new()
	sev_option.add_item("info")
	sev_option.add_item("warning")
	sev_option.add_item("error")
	sev_hbox.add_child(sev_option)
	vbox.add_child(sev_hbox)
	var text_label := Label.new()
	text_label.text = "备注:"
	vbox.add_child(text_label)
	var text_input := TextEdit.new()
	text_input.custom_minimum_size = Vector2(280, 60)
	vbox.add_child(text_input)
	var btn_hbox := HBoxContainer.new()
	btn_hbox.add_spacer(true)
	var cancel_btn := Button.new()
	cancel_btn.text = "取消"
	var confirm_btn := Button.new()
	confirm_btn.text = "确认"
	btn_hbox.add_child(cancel_btn)
	btn_hbox.add_child(confirm_btn)
	vbox.add_child(btn_hbox)
	_annotation_popup.add_child(vbox)
	add_child(_annotation_popup)
	_annotation_popup.visible = false
	cancel_btn.pressed.connect(func():
		_annotation_popup.visible = false
	)
	confirm_btn.pressed.connect(func():
		_add_annotation_from_popup(sev_option.selected, text_input.text.strip_edges())
		_annotation_popup.visible = false
	)


func _add_annotation_from_popup(sev_index: int, text: String) -> void:
	if text.is_empty():
		return
	var severity := ["info", "warning", "error"][sev_index] if sev_index < 3 else "info"
	for idx in _selection:
		var ann := Annotation.new(idx, text, severity)
		_annotations.append(ann)
		annotation_added.emit(idx, text, severity)
	var cmd := begin_command("annotation", "添加标注: %s" % text)
	cmd.before = {}
	cmd.after = {"annotation_count": _annotations.size()}
	commit_command(cmd)
	queue_redraw()


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
	if snapshot.has("indices"):
		var items: Array = snapshot["indices"]
		for item in items:
			var idx: int = item["index"]
			if idx >= 0 and idx < _notes.size():
				_notes[idx].pitch = item["pitch"]
				_notes[idx].start_time = item["start_time"]
				_notes[idx].duration = item["duration"]
	elif snapshot.has("deleted_note"):
		_notes.insert(snapshot["index"], snapshot["deleted_note"])
	elif snapshot.has("deleted_items"):
		var items: Array = snapshot["deleted_items"]
		var sorted_items := items.duplicate()
		sorted_items.sort_custom(func(a, b): return a["index"] > b["index"])
		for item in sorted_items:
			_notes.insert(item["index"], item["note_data"])
	elif snapshot.has("pitch_changes"):
		for item in snapshot["pitch_changes"]:
			var idx: int = item["index"]
			if idx >= 0 and idx < _notes.size():
				_notes[idx].pitch = item["pitch"]
	elif snapshot.has("velocity_changes"):
		for item in snapshot["velocity_changes"]:
			var idx: int = item["index"]
			if idx >= 0 and idx < _notes.size():
				_notes[idx].velocity = item["velocity"]
	elif snapshot.has("muted_indices"):
		for idx in snapshot["muted_indices"]:
			if _muted_indices.find(idx) < 0:
				_muted_indices.append(idx)
	elif snapshot.has("added_index"):
		_notes.remove_at(snapshot["added_index"])
	elif snapshot.has("index") and snapshot.has("note_data"):
		var idx: int = snapshot["index"]
		if idx >= 0 and idx < _notes.size():
			_notes[idx] = snapshot["note_data"]
		else:
			push_warning("Undo/redo: snapshot index %d out of bounds (size %d)" % [idx, _notes.size()])