## 钢琴卷帘 — MIDI 音符可视化
@tool
class_name PianoRoll
extends Control


## 点击卷帘请求跳转到指定时间位置
signal seek_requested(position: float)

## 播放位置变化（供刻度尺显示播放头）
signal playback_position_changed(time: float)

## 音符被修改（触发导出脏标记）
signal note_edited()

## 请求导出 MIDI
signal export_requested(notes: Array, path: String)

## 添加标注
signal annotation_added(note_index: int, text: String, severity: String)

## 请求导出 Agent 反馈 JSON
signal agent_feedback_requested(feedback: Dictionary, path: String)

## 请求导出 ABC 记谱法
signal abc_export_requested()

## 模式切换
signal mode_changed(new_mode: int)

## 编辑模式切换（向后兼容）
signal editing_changed(enabled: bool)

## 缩放/滚动状态变更（给 ruler 用）
signal view_offset_changed(view_offset: float, zoom_level: float, pps: float, duration: float)

## 轨道变更（新增轨道时通知 ClefStation 同步）
signal track_changed(channel: int, preset: int)

## 选中状态变更（给 VelocityLane 用）
signal selection_changed(indices: Array[int])

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

	func duplicate() -> RollNote:
		return RollNote.new(channel, pitch, start_time, duration, velocity)


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
const _EDGE_HANDLE_WIDTH: float = 8.0
const _EDGE_HANDLE_COLOR := Color(0.3, 0.9, 1.0, 0.85)
const _EDGE_HANDLE_HOVER_COLOR := Color(1.0, 1.0, 1.0, 0.95)

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

## 悬停的边缘（"none" | "left" | "right"）
var _hovered_edge: String = "none"

## 框选状态
var _box_selecting: bool = false
var _box_select_start: Vector2 = Vector2.ZERO
var _box_select_end: Vector2 = Vector2.ZERO

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

var _actions: PianoRollActions = null

var _annotations: Array[Annotation] = []
var _annotation_popup: PanelContainer = null
var _annotation_text_input: TextEdit = null

## 屏蔽（逐音符静音）索引
var _muted_indices: Array[int] = []

## 临时音符（试听用，不写入 MIDI）
var _temp_notes: Array[RollNote] = []	## deprecated, keep compat

## drag-to-create note state
var _creating_note: bool = false
var _create_pitch: int = 60
var _create_start_time: float = 0.0
var _preview_note: RollNote = null	## creation preview

## 剪贴板
var _clipboard: Array[RollNote] = []
var _clipboard_ref_time: float = 0.0
var _clipboard_ref_pitch: int = 60

## 当前选中轨道
var _active_channel: int = 0

enum Mode { PLAYBACK, EDIT, FEEDBACK }
var _mode: Mode = Mode.PLAYBACK

enum EditSubMode { SELECT }
var _edit_sub_mode: EditSubMode = EditSubMode.SELECT

var _playing: bool = false
## 水平缩放与滚动
var _zoom_level: float = 1.0
var _view_offset: float = 0.0
var _h_scroll: HScrollBar = null
var _v_scroll: VScrollBar = null
const _ZOOM_MIN: float = 0.1
const _ZOOM_MAX: float = 10.0
const _SCROLL_BAR_HEIGHT: float = 16.0
const _V_SCROLL_BAR_WIDTH: float = 16.0

## 垂直缩放（Shift+Wheel + VScrollBar）
var _vertical_zoom: float = 1.0
var _pitch_offset: int = 0
const _VERT_ZOOM_MIN: float = 0.3
const _VERT_ZOOM_MAX: float = 4.0

## 中键拖拽平移
var _panning: bool = false
var _pan_start_pos: Vector2 = Vector2.ZERO
var _pan_start_offset: float = 0.0
var _pan_start_pitch_offset: int = 0

## 网格吸附
var snap_enabled: bool = false
var _snap_interval: float = 0.1

var snap_interval: float:
	get: return _snap_interval
	set(v):
		_snap_interval = maxf(0.001, v)


func _ready() -> void:
	clip_contents = true
	custom_minimum_size = Vector2i(0, 160)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	mouse_default_cursor_shape = Control.CURSOR_ARROW
	_legend_popup = PopupMenu.new()
	_legend_popup.add_item(l10n.t("Switch Instrument"), 0)
	_legend_popup.add_item(l10n.t("Select All Notes"), 1)
	_legend_popup.id_pressed.connect(_on_legend_popup_id_pressed)
	add_child(_legend_popup)
	_file_dialog = FileDialog.new()
	_file_dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE
	_file_dialog.access = FileDialog.ACCESS_FILESYSTEM
	_file_dialog.filters = PackedStringArray(["*.mid ; MIDI Files"])
	_file_dialog.title = l10n.t("Export MIDI")
	_file_dialog.current_dir = ProjectSettings.globalize_path("res://addons/clef/output/")
	_file_dialog.file_selected.connect(_on_export_file_selected)
	add_child(_file_dialog)
	_feedback_dialog = FileDialog.new()
	_feedback_dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE
	_feedback_dialog.access = FileDialog.ACCESS_FILESYSTEM
	_feedback_dialog.filters = PackedStringArray(["*.json ; JSON Files"])
	_feedback_dialog.title = l10n.t("Export Agent Feedback")
	_feedback_dialog.current_dir = ProjectSettings.globalize_path("res://addons/clef/output/")
	_feedback_dialog.file_selected.connect(_on_feedback_file_selected)
	add_child(_feedback_dialog)
	_actions = PianoRollActions.new(self)
	_actions.create_context_menu()
	_create_h_scroll()
	_create_v_scroll()


# ─── 公共 API ─────────────────────────────────────────────

## 设置音符数据并刷新
func set_notes(notes: Array[RollNote], duration: float) -> void:
	_notes = notes
	_undo_stack.clear()
	_redo_stack.clear()
	_selection.clear()
	selection_changed.emit(_selection)
	_annotations.clear()
	_muted_indices.clear()
	_hovered_note = -1
	_duration = duration
	_zoom_level = 1.0
	_view_offset = 0.0
	_vertical_zoom = 1.0
	_pitch_offset = 0
	_collect_active_channels()
	_recalc_layout()
	_notify_view_changed()
	queue_redraw()


## 获取当前音符数组
func get_notes() -> Array[RollNote]:
	return _notes


## 设置通道乐器映射 (channel -> preset_index)
func set_channel_instruments(instruments: Dictionary) -> void:
	_channel_instruments = instruments
	queue_redraw()


## 获取通道乐器映射
func get_channel_instruments() -> Dictionary:
	return _channel_instruments


## 设置通道静音状态（由 MiniMixer 触发）
func set_channel_muted(channel: int, muted: bool) -> void:
	if muted:
		_muted_channels[channel] = true
	else:
		_muted_channels.erase(channel)
	queue_redraw()


func is_channel_muted(channel: int) -> bool:
	return _muted_channels.has(channel)


## 清除所有静音状态（加载新文件时调用）
func clear_muted_channels() -> void:
	_muted_channels.clear()
	queue_redraw()


## 外部修改音符 velocity（带 undo 快照）
func set_note_velocity(note_index: int, new_velocity: int) -> void:
	if note_index < 0 or note_index >= _notes.size():
		return
	var old_velocity := _notes[note_index].velocity
	if old_velocity == new_velocity:
		return
	var cmd := begin_command("property", l10n.t("Velocity → %d") % new_velocity)
	cmd.before = {"velocity_changes": [{"index": note_index, "velocity": old_velocity}]}
	_notes[note_index].velocity = new_velocity
	cmd.after = {"velocity_changes": [{"index": note_index, "velocity": new_velocity}]}
	commit_command(cmd)
	note_edited.emit()
	queue_redraw()
## 更新播放头位置
func set_playback_position(position: float, force: bool = false) -> void:
	if _mode == Mode.EDIT and not force and not _playing:
		return
	_playback_position = position
	playback_position_changed.emit(position)
	# 自动滚动：播放头接近边缘时平移视图
	if _visible_time_range() < _duration:
		var margin := _visible_time_range() * 0.1
		if position < _view_offset + margin:
			_view_offset = maxf(0.0, position - margin)
			_update_scroll_bars()
			_notify_view_changed()
		elif position > _view_offset + _visible_time_range() - margin:
			var max_off := maxf(0.0, _duration - _visible_time_range())
			_view_offset = minf(max_off, position - _visible_time_range() + margin)
			_update_scroll_bars()
			_notify_view_changed()
	queue_redraw()

## 清空所有状态
func clear_notes() -> void:
	_notes.clear()
	_undo_stack.clear()
	_redo_stack.clear()
	_selection.clear()
	selection_changed.emit(_selection)
	_annotations.clear()
	_hovered_note = -1
	_duration = 0.0
	_playback_position = -1.0
	_min_pitch = 0
	_max_pitch = 127
	_pixels_per_second = 100.0
	_pixels_per_note = 10.0
	_zoom_level = 1.0
	_view_offset = 0.0
	_vertical_zoom = 1.0
	_pitch_offset = 0
	_active_channels.clear()
	_channel_instruments.clear()
	_muted_channels.clear()
	_muted_indices.clear()
	queue_redraw()


## 切换模式（核心入口）
func set_mode(new_mode: Mode) -> void:
	if _mode == new_mode:
		return
	_mode = new_mode
	if new_mode == Mode.EDIT:
		_playback_position = -1.0
		_playing = false
	elif new_mode == Mode.PLAYBACK:
		_selection.clear()
		selection_changed.emit(_selection)
	elif new_mode == Mode.FEEDBACK:
		_selection.clear()
		selection_changed.emit(_selection)
	mode_changed.emit(new_mode)
	editing_changed.emit(new_mode == Mode.EDIT)
	if is_instance_valid(_actions):
		_actions._rebuild_context_menu()
	queue_redraw()


func set_editing(enabled: bool) -> void:
	set_mode(Mode.EDIT if enabled else Mode.PLAYBACK)


func set_playing(playing: bool) -> void:
	if _playing != playing:
		_playing = playing
		queue_redraw()

func is_editing() -> bool:
	return _mode == Mode.EDIT


func is_feedback_mode() -> bool:
	return _mode == Mode.FEEDBACK


func is_playing() -> bool:
	return _playing

func set_hovered_note(idx: int) -> void:
	_hovered_note = idx
	queue_redraw()

# ─── 坐标映射 ─────────────────────────────────────────────

func _effective_pps() -> float:
	return _pixels_per_second * _zoom_level


func _effective_ppn() -> float:
	return _pixels_per_note * _vertical_zoom


func _time_to_x(t: float) -> float:
	return (t - _view_offset) * _effective_pps()


func _pixel_to_time(px: float) -> float:
	var epps := _effective_pps()
	if epps <= 0.0: return 0.0
	return px / epps + _view_offset


func _pitch_to_y(pitch: int) -> float:
	var note_h := _effective_ppn()
	return _LEGEND_HEIGHT + float(_max_pitch - pitch) * note_h - float(_pitch_offset) * note_h


func _y_to_pitch(py: float) -> int:
	var note_h := _effective_ppn()
	if note_h <= 0.0: return _max_pitch
	return _max_pitch - int((py - _LEGEND_HEIGHT) / note_h) + _pitch_offset


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
		_clamp_view_offset()
		_clamp_pitch_offset()
		_update_scroll_bars()
		_notify_view_changed()
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
	# 像素/秒：整首歌适配宽度（基准，zoom=1.0 时整首可见）
	var w := float(size.x)
	if w > 0.0 and _duration > 0.0:
		_pixels_per_second = w / _duration
	# 像素/音高：音域适配高度（减去图例+滚动条）
	var h := float(size.y) - _LEGEND_HEIGHT - _SCROLL_BAR_HEIGHT
	var note_range := _max_pitch - _min_pitch + 1
	if h > 0.0 and note_range > 0:
		_pixels_per_note = h / float(note_range)
	_clamp_view_offset()
	_clamp_pitch_offset()
	_update_scroll_bars()
	_notify_view_changed()



# ─── 生命周期 ─────────────────────────────────────────────

func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED:
		_reposition_scroll_bars()
		_recalc_layout()
		queue_redraw()


func _shortcut_input(event: InputEvent) -> void:
	if _mode != Mode.EDIT:
		return
	var key := event as InputEventKey
	if key == null or not key.pressed:
		return
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
	# Ctrl+C — 复制选中音符
	if key.ctrl_pressed and not key.shift_pressed and key.keycode == KEY_C:
		if not _selection.is_empty():
			get_viewport().set_input_as_handled()
			var sorted_sel := _selection.duplicate()
			sorted_sel.sort()
			_clipboard.clear()
			_clipboard_ref_time = INF
			_clipboard_ref_pitch = 60
			for idx in sorted_sel:
				if idx >= 0 and idx < _notes.size():
					var n: RollNote = _notes[idx]
					_clipboard.append(n.duplicate())
					if n.start_time < _clipboard_ref_time:
						_clipboard_ref_time = n.start_time
					if n.pitch < _clipboard_ref_pitch:
						_clipboard_ref_pitch = n.pitch
			if _clipboard_ref_time == INF:
				_clipboard_ref_time = 0.0
		return
	# Ctrl+V — 粘贴音符
	if key.ctrl_pressed and not key.shift_pressed and key.keycode == KEY_V:
		if _clipboard.is_empty():
			return
		get_viewport().set_input_as_handled()
		var mouse_pos := get_local_mouse_position()
		var mouse_in_area := Rect2(Vector2.ZERO, size).has_point(mouse_pos)
		var target_time: float
		var target_pitch: int
		if mouse_in_area:
			target_time = _pixel_to_time(mouse_pos.x)
			target_pitch = _y_to_pitch(mouse_pos.y)
		else:
			target_time = _playback_position if _playback_position >= 0.0 else _view_offset
			target_pitch = 60  # fallback C4
		var time_offset := target_time - _clipboard_ref_time
		var pitch_offset := target_pitch - _clipboard_ref_pitch
		var cmd := begin_command("add", "粘贴 %d 个音符" % _clipboard.size())
		var added_indices: Array[int] = []
		_selection.clear()
		for cn in _clipboard:
			var new_note := RollNote.new(
				_active_channel,
				clampi(cn.pitch + pitch_offset, 0, 127),
				maxf(0.0, cn.start_time + time_offset),
				cn.duration,
				cn.velocity
			)
			_notes.append(new_note)
			added_indices.append(_notes.size() - 1)
			_selection.append(_notes.size() - 1)
		selection_changed.emit(_selection)
		cmd.before = {"added_indices": added_indices.duplicate()}
		cmd.after = {}
		commit_command(cmd)
		queue_redraw()
		return
	if key.keycode == KEY_DELETE and not _selection.is_empty():
		get_viewport().set_input_as_handled()
		_actions._delete_selected()
		return
	# Ctrl+= / Ctrl+- 水平缩放
	if key.ctrl_pressed and not key.shift_pressed and key.keycode == KEY_EQUAL:
		get_viewport().set_input_as_handled()
		_zoom_level = minf(_ZOOM_MAX, _zoom_level * 1.2)
		_apply_view_change()
		return
	if key.ctrl_pressed and not key.shift_pressed and key.keycode == KEY_MINUS:
		get_viewport().set_input_as_handled()
		_zoom_level = maxf(_ZOOM_MIN, _zoom_level / 1.2)
		_apply_view_change()
		return
	# Home / End 滚动
	if not key.ctrl_pressed and key.keycode == KEY_HOME:
		get_viewport().set_input_as_handled()
		_view_offset = 0.0
		_apply_view_change()
		return
	if not key.ctrl_pressed and key.keycode == KEY_END:
		get_viewport().set_input_as_handled()
		if _duration > 0.0:
			_view_offset = maxf(0.0, _duration - _visible_time_range())
		_apply_view_change()
		return
	# Ctrl+Home 重置缩放
	if key.ctrl_pressed and key.keycode == KEY_HOME:
		get_viewport().set_input_as_handled()
		_zoom_level = 1.0
		_vertical_zoom = 1.0
		_view_offset = 0.0
		_pitch_offset = 0
		_recalc_layout()
		queue_redraw()
		return


func _unhandled_key_input(event: InputEvent) -> void:
	# 非冲突按键已迁移到 _shortcut_input
	# 保留此函数以便未来添加非快捷键处理
	pass

func _gui_input(event: InputEvent) -> void:
	# Legend bar 交互
	if event is InputEventMouseButton and event.position.y < _LEGEND_HEIGHT:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			var plus_x := _get_plus_button_x()
			var export_x := size.x - 28.0
			var feedback_x := size.x - 56.0
			# 反馈按钮
			if mb.position.x >= feedback_x and mb.position.x < export_x:
				if _mode == Mode.FEEDBACK:
					_show_feedback_dialog()
					accept_event()
					return
			# 导出按钮
			if mb.position.x >= export_x:
				if _mode == Mode.EDIT:
					_show_export_dialog()
				accept_event()
				return
			# "+" 按钮（仅编辑模式）
			if _mode == Mode.EDIT and mb.position.x >= plus_x and mb.position.x < export_x:
				_open_gm_selector_popup()
				accept_event()
				return
			# 轨道切换
			if _mode == Mode.EDIT:
				_handle_legend_click(mb.position.x)
				accept_event()
				return
		if mb.pressed and mb.button_index == MOUSE_BUTTON_RIGHT and _mode == Mode.EDIT:
				var ch := _hit_test_legend(mb.position.x)
				if ch >= 0:
					_legend_context_channel = ch
					var mouse_screen := DisplayServer.mouse_get_position()
					_legend_popup.popup(Rect2i(mouse_screen + Vector2i(2, 2), Vector2i()))
					accept_event()
					return
	if event is InputEventMouseButton:
		_handle_mouse_button(event as InputEventMouseButton)
	elif event is InputEventMouseMotion:
		_handle_mouse_motion(event as InputEventMouseMotion)


func _handle_mouse_button(mb: InputEventMouseButton) -> void:
	# Ctrl+Wheel 水平缩放
	if mb.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN] and mb.ctrl_pressed:
		var mouse_time := _pixel_to_time(mb.position.x)
		if mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			_zoom_level = minf(_ZOOM_MAX, _zoom_level * 1.15)
		else:
			_zoom_level = maxf(_ZOOM_MIN, _zoom_level / 1.15)
		var new_epps := _effective_pps()
		if new_epps > 0.0:
			_view_offset = mouse_time - mb.position.x / new_epps
		_apply_view_change()
		get_viewport().set_input_as_handled()
		return
	# Shift+Wheel 垂直缩放（锚定鼠标位置）
	if mb.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN] and mb.shift_pressed and not mb.ctrl_pressed:
		var mouse_y := mb.position.y
		var old_ppn := _effective_ppn()
		if mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			_vertical_zoom = minf(_VERT_ZOOM_MAX, _vertical_zoom * 1.15)
		else:
			_vertical_zoom = maxf(_VERT_ZOOM_MIN, _vertical_zoom / 1.15)
		var new_ppn := _effective_ppn()
		if old_ppn > 0.0 and new_ppn > 0.0:
			_pitch_offset = int(float(_pitch_offset) + (mouse_y - _LEGEND_HEIGHT) * (1.0 / new_ppn - 1.0 / old_ppn))
		_clamp_pitch_offset()
		_update_scroll_bars()
		queue_redraw()
		get_viewport().set_input_as_handled()
		return
	# 中键拖拽平移
	if mb.button_index == MOUSE_BUTTON_MIDDLE and mb.pressed:
		_panning = true
		_pan_start_pos = mb.position
		_pan_start_offset = _view_offset
		_pan_start_pitch_offset = _pitch_offset
		get_viewport().set_input_as_handled()
		return
	if mb.button_index == MOUSE_BUTTON_MIDDLE and not mb.pressed and _panning:
		_panning = false
		get_viewport().set_input_as_handled()
		return
	# 左键
	if mb.button_index == MOUSE_BUTTON_LEFT:
		if mb.pressed:
			_handle_left_press(mb)
		else:
			_handle_left_release(mb)
		return
	# 右键菜单
	if mb.button_index == MOUSE_BUTTON_RIGHT and mb.pressed:
		_handle_right_click(mb)


func _handle_left_press(mb: InputEventMouseButton) -> void:
	if _mode == Mode.PLAYBACK:
		_selection.clear()
		selection_changed.emit(_selection)
		queue_redraw()
		var t := _pixel_to_time(mb.position.x)
		if _duration > 0.0 and t >= 0.0 and t <= _duration:
			seek_requested.emit(t)
		return
	# EDITING 和 FEEDBACK：允许选中
	var hit := _hit_test(mb.position)
	if hit["index"] >= 0:
		if mb.shift_pressed:
			var idx: int = hit["index"]
			var found := _selection.find(idx)
			if found >= 0:
				_selection.remove_at(found)
			else:
				_selection.append(idx)
			selection_changed.emit(_selection)
		elif hit["index"] in _selection:
			pass  # 点击已选中音符，保持多选状态
		else:
			_selection.clear()
			_selection.append(hit["index"])
			selection_changed.emit(_selection)
		# 仅编辑模式开始拖拽
		if _mode == Mode.EDIT:
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
		if _mode == Mode.EDIT and mb.alt_pressed:
			# Alt+点击 → 创建音符
			_creating_note = true
			_create_pitch = clampi(_y_to_pitch(mb.position.y), 0, 127)
			_create_start_time = maxf(0.0, _pixel_to_time(mb.position.x))
			if snap_enabled:
				_create_start_time = round(_create_start_time / snap_interval) * snap_interval
			_preview_note = null
			queue_redraw()
		else:
			# 框选（原行为）
			_selection.clear()
			selection_changed.emit(_selection)
			_box_selecting = true
			_box_select_start = mb.position
			_box_select_end = mb.position
			queue_redraw()


func _handle_left_release(_mb: InputEventMouseButton) -> void:
	# confirm drag-to-create note
	if _creating_note:
		_creating_note = false
		if _preview_note != null and _preview_note.duration >= 0.05:
			var new_note := _preview_note.duplicate()
			_notes.append(new_note)
			var idx := _notes.size() - 1
			var cmd := begin_command("add", "创建音符")
			cmd.before = {"added_index": idx}
			cmd.after = {}
			commit_command(cmd)
			_selection.clear()
			_selection.append(idx)
			selection_changed.emit(_selection)
		else:
			# single click -> default 1 beat note
			var beat_dur := 0.5
			var new_note := RollNote.new(_active_channel, _create_pitch, _create_start_time, beat_dur, 100)
			_notes.append(new_note)
			var idx := _notes.size() - 1
			var cmd := begin_command("add", "创建音符")
			cmd.before = {"added_index": idx}
			cmd.after = {}
			commit_command(cmd)
			_selection.clear()
			_selection.append(idx)
			selection_changed.emit(_selection)
		_preview_note = null
		queue_redraw()
		note_edited.emit()
		return
	if _dragging:
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
		return
	if _box_selecting:
		_box_selecting = false
		var sel_rect := Rect2(
			minf(_box_select_start.x, _box_select_end.x),
			minf(_box_select_start.y, _box_select_end.y),
			absf(_box_select_end.x - _box_select_start.x),
			absf(_box_select_end.y - _box_select_start.y)
		)
		if sel_rect.size.x > 2.0 and sel_rect.size.y > 2.0:
			for i in _notes.size():
				var n := _notes[i]
				if _muted_channels.has(n.channel):
					continue
				var nx := _time_to_x(n.start_time)
				var nw := n.duration * _effective_pps()
				var ny := _pitch_to_y(n.pitch + 1)
				var nh := _effective_ppn()
				if sel_rect.intersects(Rect2(nx, ny, nw, nh)):
					if not _selection.has(i):
						_selection.append(i)
		selection_changed.emit(_selection)
		queue_redraw()


func _handle_right_click(mb: InputEventMouseButton) -> void:
	if _mode == Mode.PLAYBACK:
		return
	var hit := _hit_test(mb.position)
	if hit["index"] >= 0:
		if not _selection.has(hit["index"]):
			_selection.clear()
			_selection.append(hit["index"])
			selection_changed.emit(_selection)
			queue_redraw()
		var mouse_screen := DisplayServer.mouse_get_position()
		_context_menu.popup(Rect2i(mouse_screen + Vector2i(2, 2), Vector2i()))
		get_viewport().set_input_as_handled()


func _handle_mouse_motion(event: InputEventMouseMotion) -> void:
	if _panning:
		var delta: Vector2 = event.position - _pan_start_pos
		var epps := _effective_pps()
		if epps > 0.0:
			_view_offset = _pan_start_offset - delta.x / epps
		var eppn := _effective_ppn()
		if eppn > 0.0:
			_pitch_offset = _pan_start_pitch_offset + int(delta.y / eppn)
		_apply_view_change()
	elif _box_selecting:
		_box_select_end = event.position
		queue_redraw()
	elif _creating_note and event.button_mask & MOUSE_BUTTON_MASK_LEFT:
		var current_time := _pixel_to_time(event.position.x)
		if snap_enabled:
			current_time = round(current_time / snap_interval) * snap_interval
		var start_t := minf(_create_start_time, current_time)
		var dur := absf(current_time - _create_start_time)
		_preview_note = RollNote.new(_active_channel, _create_pitch, start_t, dur, 100)
		queue_redraw()
	elif _dragging:
		_drag_update(event.position)
	else:
		var hit := _hit_test(event.position)
		var new_note: int =  hit["index"]
		var new_edge: String = hit["edge"] if _mode == Mode.EDIT and new_note >= 0 and _selection.has(new_note) else "none"
		if new_note != _hovered_note or new_edge != _hovered_edge:
			_hovered_note = new_note
			_hovered_edge = new_edge
			mouse_default_cursor_shape = Control.CURSOR_HSPLIT if _hovered_edge != "none" else Control.CURSOR_ARROW
			queue_redraw()

func _drag_update(pos: Vector2) -> void:
	var delta: Vector2 = pos - _drag_start_pos
	match _drag_type:
		1:  # MOVE
			var pitch_delta := int(delta.y / _effective_ppn())
			var time_delta: float = delta.x / _effective_pps()
			if snap_enabled:
				time_delta = round(time_delta / snap_interval) * snap_interval
			for orig in _drag_original_notes:
				var idx: int = orig["index"]
				if idx >= 0 and idx < _notes.size():
					_notes[idx].pitch = orig["pitch"] - pitch_delta
					_notes[idx].start_time = orig["start_time"] + time_delta
			queue_redraw()
		2:  # RESIZE_LEFT
			var time_delta: float = delta.x / _effective_pps()
			if snap_enabled:
				time_delta = round(time_delta / snap_interval) * snap_interval
			var min_start: float = _drag_original_notes[0]["start_time"]
			var min_dur: float = _drag_original_notes[0]["duration"]
			for orig in _drag_original_notes:
				if orig["start_time"] < min_start: min_start = orig["start_time"]
				if orig["duration"] < min_dur: min_dur = orig["duration"]
			time_delta = clampf(time_delta, -min_start, min_dur)			
			for orig in _drag_original_notes:
				var idx: int = orig["index"]
				if idx >= 0 and idx < _notes.size():
					_notes[idx].start_time = orig["start_time"] + time_delta
					_notes[idx].duration = orig["duration"] - time_delta
			queue_redraw()
		3:  # RESIZE_RIGHT
			var time_delta: float = delta.x / _effective_pps()
			if snap_enabled:
				time_delta = round(time_delta / snap_interval) * snap_interval
			time_delta = maxf(time_delta, -_drag_original_notes[0]["duration"])
			for orig in _drag_original_notes:
				var idx: int = orig["index"]
				if idx >= 0 and idx < _notes.size():
					_notes[idx].duration = orig["duration"] + time_delta
			queue_redraw()

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
	# 八度网格线 + 时间网格线
	_draw_pitch_grid()
	# 音符矩形
	_draw_notes()
	# 播放头
	_draw_playback_cursor()
	# 标注（仅反馈模式）
	if _mode == Mode.FEEDBACK:
		_actions.draw_annotations()

	# 框选矩形
	if _box_selecting:
		var sel_rect := Rect2(
			minf(_box_select_start.x, _box_select_end.x),
			minf(_box_select_start.y, _box_select_end.y),
			absf(_box_select_end.x - _box_select_start.x),
			absf(_box_select_end.y - _box_select_start.y)
		)
		draw_rect(sel_rect, Color(1, 1, 1, 0.15))
		draw_rect(sel_rect, Color(1, 1, 1, 0.6), false, 1.0)


func _draw_legend() -> void:
	# 背景
	draw_rect(Rect2(0, 0, size.x, _LEGEND_HEIGHT), _LEGEND_BG)
	# 分隔线
	draw_line(Vector2(0, _LEGEND_HEIGHT), Vector2(size.x, _LEGEND_HEIGHT), Color(0.2, 0.2, 0.25))

	var x := 8.0
	var font := ThemeDB.fallback_font
	var font_size := 12
	var plus_width := 28.0

	for ch in _active_channels:
		if _muted_channels.has(ch):
			continue
		var preset: int = _channel_instruments.get(ch, 0)
		var name: String
		if ch == 9:
			name = "Ch%d" % ch
		else:
			name = "Ch%d %s" % [ch, _GM_NAMES[preset] if preset < _GM_NAMES.size() else "?"]
		var color := ChannelColors.COLORS[ch % 16]
		var text_w := font.get_string_size(name, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
		var label_w := text_w + 28

		# 防止标签超出按钮区域
		if x + label_w > size.x - plus_width * 2 - 16:
			break

		# 选中高亮背景
		if ch == _active_channel:
			draw_rect(Rect2(x - 2, 2, label_w, _LEGEND_HEIGHT - 4), Color(0.15, 0.15, 0.2))
			draw_rect(Rect2(x - 2, 2, label_w, _LEGEND_HEIGHT - 4), Color(1.0, 1.0, 1.0, 0.6), false, 1.0)

		# 色块
		draw_rect(Rect2(x, 5, 18, 18), color)
		if ch == _active_channel:
			draw_rect(Rect2(x, 5, 18, 18), Color(1.0, 1.0, 1.0, 0.8), false, 1.5)

		# 文字
		var text_color := Color(1.0, 1.0, 1.0) if ch == _active_channel else Color(0.7, 0.7, 0.75)
		draw_string(font, Vector2(x + 24, _LEGEND_HEIGHT / 2 + font_size / 2 - 1),
			name, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, text_color)

		x += label_w

	# "+" 按钮（跟随轨道末尾）
	var plus_rect := Rect2(x + 4, 0, plus_width, _LEGEND_HEIGHT)
	draw_rect(plus_rect, Color(0.12, 0.12, 0.16) if _mode == Mode.EDIT else Color(0.08, 0.08, 0.1))
	draw_line(Vector2(plus_rect.position.x, 0),
		Vector2(plus_rect.position.x, _LEGEND_HEIGHT), Color(0.2, 0.2, 0.25))
	var ps := font.get_string_size("+", HORIZONTAL_ALIGNMENT_CENTER, -1, 20)
	draw_string(font, Vector2(plus_rect.position.x + plus_width / 2 - ps.x / 2, _LEGEND_HEIGHT / 2 + 5),
		"+", HORIZONTAL_ALIGNMENT_CENTER, -1, 20, Color(0.6, 0.8, 0.6) if _mode == Mode.EDIT else Color(0.4, 0.4, 0.4))

	# "⩩" 反馈按钮
	var feedback_rect := Rect2(size.x - plus_width * 2, 0, plus_width, _LEGEND_HEIGHT)
	var fb_active := _mode == Mode.FEEDBACK
	draw_rect(feedback_rect, Color(0.12, 0.12, 0.16) if fb_active else Color(0.08, 0.08, 0.1))
	draw_line(Vector2(feedback_rect.position.x, 0),
		Vector2(feedback_rect.position.x, _LEGEND_HEIGHT), Color(0.2, 0.2, 0.25))
	var fbs := font.get_string_size("⩩", HORIZONTAL_ALIGNMENT_CENTER, -1, 20)
	draw_string(font, Vector2(feedback_rect.position.x + plus_width / 2 - fbs.x / 2, _LEGEND_HEIGHT / 2 + 5),
		"⩩", HORIZONTAL_ALIGNMENT_CENTER, -1, 20, Color(0.9, 0.7, 0.4) if fb_active else Color(0.4, 0.4, 0.4))

	# "⤓" 导出按钮（固定右端）
	var export_rect := Rect2(size.x - plus_width, 0, plus_width, _LEGEND_HEIGHT)
	draw_rect(export_rect, Color(0.12, 0.12, 0.16) if _mode == Mode.EDIT else Color(0.08, 0.08, 0.1))
	draw_line(Vector2(export_rect.position.x, 0),
		Vector2(export_rect.position.x, _LEGEND_HEIGHT), Color(0.2, 0.2, 0.25))
	var es := font.get_string_size("⤓", HORIZONTAL_ALIGNMENT_CENTER, -1, 20)
	draw_string(font, Vector2(export_rect.position.x + plus_width / 2 - es.x / 2, _LEGEND_HEIGHT / 2 + 5),
		"⤓", HORIZONTAL_ALIGNMENT_CENTER, -1, 20, Color(0.6, 0.7, 0.9) if _mode == Mode.EDIT else Color(0.4, 0.4, 0.4))


func _draw_pitch_grid() -> void:
	var bottom_y := size.y - _SCROLL_BAR_HEIGHT
	var right_x := size.x - _V_SCROLL_BAR_WIDTH
	# 水平音高线
	for pitch in range(_min_pitch, _max_pitch + 1):
		var y := _pitch_to_y(pitch)
		if y < _LEGEND_HEIGHT or y > bottom_y:
			continue
		var is_c := pitch % 12 == 0
		var color := _GRID_C_COLOR if is_c else _GRID_LINE_COLOR
		draw_line(Vector2(0, y), Vector2(size.x, y), color)
	# 竖直时间网格线
	var interval := _get_time_interval()
	if interval <= 0.0 or _duration <= 0.0:
		return
	var start_t := floorf(_view_offset / interval) * interval
	var end_t := _view_offset + _visible_time_range()
	var t := start_t
	while t <= end_t:
		var x := _time_to_x(t)
		if x >= 0.0 and x <= size.x:
			draw_line(Vector2(x, _LEGEND_HEIGHT), Vector2(x, bottom_y), _GRID_LINE_COLOR)
		t += interval


func _draw_notes() -> void:
	var sel_set: Dictionary = {}
	for idx in _selection:
		sel_set[idx] = true

	var visible_start := _view_offset
	var visible_end := _view_offset + _visible_time_range()
	var right_x := size.x - _V_SCROLL_BAR_WIDTH
	var bottom_y := size.y - _SCROLL_BAR_HEIGHT
	var eppn := _effective_ppn()

	for i in _notes.size():
		var note := _notes[i]
		if _muted_channels.has(note.channel):
			continue
		# 时间裁剪
		if note.start_time + note.duration < visible_start or note.start_time > visible_end:
			continue
		var x := _time_to_x(note.start_time)
		var w := note.duration * _effective_pps()
		if note.channel == 9:
			w = maxf(w, 2.0)
		var y := _pitch_to_y(note.pitch + 1)
		var h := eppn - 1.0
		# 空间裁剪
		if x + w < 0.0 or x > right_x or y + h < _LEGEND_HEIGHT or y > bottom_y:
			continue
		var base_color := ChannelColors.COLORS[note.channel % 16]
		var brightness := 0.5 + (float(note.velocity) / 127.0) * 0.5
		var color := Color(
			base_color.r * brightness,
			base_color.g * brightness,
			base_color.b * brightness
		)
		# 屏蔽态：半透明 + 删除线
		if is_note_muted(i):
			color.a = 0.3
			draw_rect(Rect2(x, y, w, h), color)
			draw_line(Vector2(x, y + h / 2), Vector2(x + w, y + h / 2), Color(1, 0.3, 0.3), 1.5)
			if sel_set.has(i):
				draw_rect(Rect2(x - 1, y - 1, w + 2, h + 2), Color(1, 1, 1, 0.5), false, 2.0)
			continue
		draw_rect(Rect2(x, y, w, h), color)

		# 选中高亮边框
		if sel_set.has(i):
			draw_rect(Rect2(x - 1, y - 1, w + 2, h + 2), Color(1, 1, 1, 0.9), false, 2.0)
			# 边缘拖拽手柄（仅编辑模式）
			if _mode == Mode.EDIT:
				var hw := _EDGE_HANDLE_WIDTH
				var hc := _EDGE_HANDLE_HOVER_COLOR if i == _hovered_note and _hovered_edge != "none" else _EDGE_HANDLE_COLOR
				draw_rect(Rect2(x - hw / 2.0, y, hw, h), hc)
				draw_rect(Rect2(x + w - hw / 2.0, y, hw, h), hc)

		# 悬停高亮
		if i == _hovered_note:
			draw_rect(Rect2(x, y, w, h), Color(1, 1, 1, 0.15))
			draw_rect(Rect2(x, y, w, h), Color(0.3, 0.6, 1.0, 0.9), false, 1.5)

	# creation preview note
	if _preview_note != null:
		var pn := _preview_note
		var x1 := _time_to_x(pn.start_time)
		var x2 := _time_to_x(pn.start_time + pn.duration)
		var y1 := _pitch_to_y(pn.pitch + 1)
		var y2 := _pitch_to_y(pn.pitch)
		var rect := Rect2(minf(x1, x2), minf(y1, y2), absf(x2 - x1), absf(y2 - y1))
		draw_rect(rect, Color(0.2, 0.8, 0.3, 0.5))
		draw_rect(rect, Color(0.3, 1.0, 0.4, 0.8), false, 1.0)




func _draw_playback_cursor() -> void:
	if _playback_position < 0.0 or _duration <= 0.0:
		return
	var x := _time_to_x(_playback_position)
	var bottom_y := size.y - _SCROLL_BAR_HEIGHT
	draw_line(Vector2(x, 0), Vector2(x, bottom_y), _PLAYBACK_COLOR, 2.0)


func is_note_muted(index: int) -> bool:
	return _muted_indices.find(index) >= 0

func _make_annotation(idx: int, text: String, severity: String) -> Annotation:
	return Annotation.new(idx, text, severity)

# ─── 命中检测 ─────────────────────────────────────────────

## 返回 {index: int, edge: String}，edge: "none" | "left" | "right"
func _hit_test(pos: Vector2) -> Dictionary:
	var time := _pixel_to_time(pos.x)
	for i in range(_notes.size() - 1, -1, -1):
		var n := _notes[i]
		if n.channel == 9 and _muted_channels.has(n.channel):
			continue
		# 用垂直边界匹配，而非精确音高整数匹配
		var y_top := _pitch_to_y(n.pitch + 1)
		var y_bottom := _pitch_to_y(n.pitch)
		if pos.y < y_top or pos.y >= y_bottom:
			continue
		# 音符内部命中
		if time >= n.start_time and time <= n.start_time + n.duration:
			var edge := _check_edge(pos, n)
			return {"index": i, "edge": edge}
		# 边缘区域命中（延伸到音符边界外）
		var x_left := _time_to_x(n.start_time)
		var x_right := _time_to_x(n.start_time + n.duration)
		var tolerance := _EDGE_HANDLE_WIDTH / 2.0
		if absf(pos.x - x_left) <= tolerance or absf(pos.x - x_right) <= tolerance:
			var edge := _check_edge(pos, n)
			if edge != "none":
				return {"index": i, "edge": edge}
	return {"index": -1, "edge": "none"}

func _get_plus_button_x() -> float:
	var font := ThemeDB.fallback_font
	var font_size := 12
	var x := 8.0
	for ch in _active_channels:
		if _muted_channels.has(ch):
			continue
		var preset: int = _channel_instruments.get(ch, 0)
		var name: String
		if ch == 9:
			name = "Ch%d" % ch
		else:
			name = "Ch%d %s" % [ch, _GM_NAMES[preset] if preset < _GM_NAMES.size() else "?"]
		var text_w := font.get_string_size(name, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
		var label_w := text_w + 28
		if x + label_w > size.x - 72:
			break
		x += label_w
	return x + 4


func _hit_test_legend(click_x: float) -> int:
	var font := ThemeDB.fallback_font
	var font_size := 12
	var x := 8.0
	for ch in _active_channels:
		if _muted_channels.has(ch):
			continue
		var preset: int = _channel_instruments.get(ch, 0)
		var name: String
		if ch == 9:
			name = "Ch%d" % ch
		else:
			name = "Ch%d %s" % [ch, _GM_NAMES[preset] if preset < _GM_NAMES.size() else "?"]
		var text_w := font.get_string_size(name, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
		var label_w := text_w + 28
		if x + label_w > size.x - 36:
			break
		if click_x >= x and click_x < x + label_w:
			return ch
		x += label_w
	return -1


func _handle_legend_click(click_x: float) -> void:
	var ch := _hit_test_legend(click_x)
	if ch >= 0 and _active_channel != ch:
		_active_channel = ch
		queue_redraw()
		track_changed.emit(ch, _channel_instruments.get(ch, 0))


var _gm_selector: Window = null
var _soundfont_browser: SoundfontBrowser = null
var _legend_popup: PopupMenu = null
var _legend_context_channel: int = -1
var _file_dialog: FileDialog = null
var _feedback_dialog: FileDialog = null

func set_soundfont_browser(browser: SoundfontBrowser) -> void:
	_soundfont_browser = browser


func _open_gm_selector_popup() -> void:
	if _gm_selector == null:
		_gm_selector = GMInstrumentSelector.new()
		_gm_selector.l10n = l10n
		_gm_selector.instrument_selected.connect(_on_instrument_selected)
		add_child(_gm_selector)
	# 每次打开时重新填充（SF2 可能已更换）
	var patches: Array = []
	if _soundfont_browser != null:
		patches = _soundfont_browser.get_patches()
	_gm_selector.populate(patches)
	_gm_selector.position = get_global_mouse_position() + Vector2(10, 10)
	_gm_selector.popup_centered()



func _show_feedback_dialog() -> void:
	var ts := Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "_")
	_feedback_dialog.current_path = _feedback_dialog.current_dir.path_join("agent_feedback_" + ts + ".json")
	_feedback_dialog.popup_centered(Vector2i(800, 600))


func _on_feedback_file_selected(fpath: String) -> void:
	agent_feedback_requested.emit(_actions.get_agent_feedback(), fpath)


func _show_export_dialog() -> void:
	var ts := Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "_")
	_file_dialog.current_path = _file_dialog.current_dir.path_join("edited_" + ts + ".mid")
	_file_dialog.popup_centered(Vector2i(800, 600))


func _on_export_file_selected(fpath: String) -> void:
	export_requested.emit(_notes, fpath)


func _select_channel_notes(ch: int) -> void:
	_selection.clear()
	for i in range(_notes.size()):
		if _notes[i].channel == ch:
			_selection.append(i)
	queue_redraw()
	selection_changed.emit(_selection)

func _on_legend_popup_id_pressed(id: int) -> void:
	match id:
		1:  # 选择该轨道全部音符
			_select_channel_notes(_legend_context_channel)
		0:  # 切换音色
			if _legend_context_channel < 0:
				return
			if _gm_selector == null:
				_gm_selector = GMInstrumentSelector.new()
				_gm_selector.l10n = l10n
				add_child(_gm_selector)
			if _gm_selector.instrument_selected.is_connected(_on_instrument_selected):
				_gm_selector.instrument_selected.disconnect(_on_instrument_selected)
			if not _gm_selector.instrument_selected.is_connected(_on_instrument_change_selected):
				_gm_selector.instrument_selected.connect(_on_instrument_change_selected)
			var patches: Array = []
			if _soundfont_browser != null:
				patches = _soundfont_browser.get_patches()
			_gm_selector.populate(patches)
			_gm_selector.position = get_global_mouse_position() + Vector2(10, 10)
			_gm_selector.popup_centered()


func _on_instrument_change_selected(preset: int) -> void:
	var ch := _legend_context_channel
	if ch < 0:
		return
	_channel_instruments[ch] = preset
	track_changed.emit(ch, preset)
	queue_redraw()
func _on_instrument_selected(preset: int) -> void:
	# 找最小未使用的 channel（跳过 9）
	var used_channels: Array[int] = []
	for ch in _active_channels:
		used_channels.append(ch)
	var new_ch: int = -1
	for c in range(16):
		if c == 9:
			continue
		if not c in used_channels:
			new_ch = c
			break
	if new_ch < 0:
		push_warning("Piano Roll: 轨道数已达上限")
		return

	_channel_instruments[new_ch] = preset
	if not new_ch in _active_channels:
		_active_channels.append(new_ch)
	_active_channels.sort()
	_active_channel = new_ch

	track_changed.emit(new_ch, preset)
	queue_redraw()


func _check_edge(pos: Vector2, note: RollNote) -> String:
	var x_left := _time_to_x(note.start_time)
	var x_right := _time_to_x(note.start_time + note.duration)
	var tolerance := _EDGE_HANDLE_WIDTH / 2.0
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
	selection_changed.emit(_selection)

func _redo() -> void:
	if _redo_stack.is_empty():
		return
	var cmd := _redo_stack.pop_back() as EditCommand
	_apply_snapshot(cmd.after)
	_undo_stack.append(cmd)
	_notify_edit()
	selection_changed.emit(_selection)

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
		_muted_indices = snapshot["muted_indices"].duplicate()
	elif snapshot.has("annotations"):
		_annotations = snapshot["annotations"].duplicate()
	elif snapshot.has("added_indices"):
		var indices: Array = snapshot["added_indices"]
		var sorted_indices := indices.duplicate()
		sorted_indices.sort_custom(func(a, b): return a > b)
		for idx in sorted_indices:
			if idx >= 0 and idx < _notes.size():
				_notes.remove_at(idx)
	elif snapshot.has("added_index"):
		_notes.remove_at(snapshot["added_index"])
	elif snapshot.has("index") and snapshot.has("note_data"):
		var idx: int = snapshot["index"]
		if idx >= 0 and idx < _notes.size():
			_notes[idx] = snapshot["note_data"]
		else:
			push_warning("Undo/redo: snapshot index %d out of bounds (size %d)" % [idx, _notes.size()])


# ─── 缩放与滚动辅助 ───────────────────────────────────────

func _visible_time_range() -> float:
	var epps := _effective_pps()
	if epps <= 0.0: return _duration
	return float(size.x) / epps


func _visible_pitch_count() -> int:
	var eppn := _effective_ppn()
	if eppn <= 0.0: return 1
	return int((float(size.y) - _LEGEND_HEIGHT - _SCROLL_BAR_HEIGHT) / eppn)


func _clamp_view_offset() -> void:
	if _duration <= 0.0:
		_view_offset = 0.0
		return
	var max_offset := maxf(0.0, _duration - _visible_time_range())
	_view_offset = clampf(_view_offset, 0.0, max_offset)


func _clamp_pitch_offset() -> void:
	var max_pitch_offset := maxi(0, _max_pitch - _min_pitch + 1 - _visible_pitch_count())
	_pitch_offset = clampi(_pitch_offset, 0, max_pitch_offset)


## 根据 epps 计算合适的刻度间距（与 piano_time_ruler.gd 保持同步）
func _get_time_interval() -> float:
	var epps := _effective_pps()
	if epps <= 0.0: return 1.0
	var raw := 80.0 / epps  # ~80px between ticks
	var nice := [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0]
	for n in nice:
		if n >= raw:
			return n
	return 120.0


func _apply_view_change() -> void:
	_clamp_view_offset()
	_clamp_pitch_offset()
	_update_scroll_bars()
	_notify_view_changed()
	queue_redraw()

func _create_h_scroll() -> void:
	_h_scroll = HScrollBar.new()
	_h_scroll.anchor_right = 1.0
	_h_scroll.anchor_bottom = 1.0
	_h_scroll.offset_left = 0.0
	_h_scroll.offset_right = -0.0
	_h_scroll.offset_bottom = 0.0
	_h_scroll.custom_minimum_size = Vector2i(0, int(_SCROLL_BAR_HEIGHT))
	_h_scroll.value_changed.connect(_on_h_scroll_changed)
	add_child(_h_scroll)



func _create_v_scroll() -> void:
	_v_scroll = VScrollBar.new()
	_v_scroll.anchor_right = 1.0
	_v_scroll.anchor_bottom = 1.0
	_v_scroll.custom_minimum_size = Vector2i(int(_V_SCROLL_BAR_WIDTH), 0)
	# 透明背景，避免遮挡音符内容
	_v_scroll.add_theme_stylebox_override("scroll", StyleBoxEmpty.new())
	_v_scroll.value_changed.connect(_on_v_scroll_changed)
	add_child(_v_scroll)

func _reposition_scroll_bars() -> void:
	if _h_scroll:
		_h_scroll.offset_top = size.y - _SCROLL_BAR_HEIGHT
		_h_scroll.offset_right = -_V_SCROLL_BAR_WIDTH
	if _v_scroll:
		_v_scroll.offset_left = size.x - _V_SCROLL_BAR_WIDTH
		_v_scroll.offset_right = 0.0
		_v_scroll.offset_top = _LEGEND_HEIGHT
		_v_scroll.offset_bottom = -_SCROLL_BAR_HEIGHT

func _update_scroll_bars() -> void:
	if _h_scroll and _duration > 0.0:
		_h_scroll.max_value = _duration
		_h_scroll.page = _visible_time_range()
		_h_scroll.step = 0.01
		_h_scroll.value = _view_offset
	var note_range := _max_pitch - _min_pitch + 1
	if _v_scroll and note_range > 0:
		_v_scroll.max_value = float(note_range)
		_v_scroll.page = float(_visible_pitch_count())
		_v_scroll.step = 1.0
		_v_scroll.value = float(_pitch_offset)

func _on_h_scroll_changed(value: float) -> void:
	_view_offset = value
	_notify_view_changed()
	queue_redraw()

func _on_v_scroll_changed(value: float) -> void:
	_pitch_offset = int(value)
	_notify_view_changed()
	queue_redraw()

func _notify_view_changed() -> void:
	view_offset_changed.emit(_view_offset, _zoom_level, _pixels_per_second, _duration)
