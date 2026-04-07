## Velocity Lane — 音符力度可视化编辑面板
@tool
class_name VelocityLane
extends Control


signal velocity_changed(note_index: int, new_velocity: int)
signal note_hovered(note_index: int)


## 活动通道
var active_channel: int = 0
var _mode: int = 0
## 音符数据引用（由外部通过 set_notes 设置）
var _notes: Array[PianoRoll.RollNote] = []
## 当前选中音符索引集合
var _selection: Array[int] = []
## 每个 slider 对应的 _notes 原始索引
var _slider_note_indices: Array[int] = []
## slider 控件池
var _sliders: Array[VSlider] = []
## 拖拽状态追踪
var _dragging_slider_idx: int = -1
var _drag_original_velocity: int = 0
## 防抖标记
var _rebuild_pending: bool = false
## 视图参数（与 PianoRoll 同步）
var _view_offset: float = 0.0
var _zoom_level: float = 1.0
var _pps: float = 100.0
var _duration: float = 0.0
## 左侧刻度区域宽度
const _LABEL_WIDTH: float = 32.0


func _ready() -> void:
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	clip_contents = true
	mouse_filter = Control.MOUSE_FILTER_PASS


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.08, 0.08, 0.12))
	var font := ThemeDB.fallback_font
	draw_string(font, Vector2(2, 14), "127", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color(0.35, 0.35, 0.4))
	draw_string(font, Vector2(2, size.y / 2.0 + 4), "64", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color(0.35, 0.35, 0.4))
	draw_string(font, Vector2(2, size.y - 2), "0", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color(0.35, 0.35, 0.4))
	draw_line(Vector2(_LABEL_WIDTH, size.y / 2.0), Vector2(size.x, size.y / 2.0), Color(0.2, 0.2, 0.28), 1.0, true)


func set_notes(notes: Array[PianoRoll.RollNote]) -> void:
	_notes = notes
	_rebuild_sliders()


func set_selection(indices: Array[int]) -> void:
	_selection = indices
	_update_selection_highlight()


func set_active_channel(channel: int) -> void:
	if active_channel == channel:
		return
	active_channel = channel
	_rebuild_sliders()


func set_edit_mode(mode: int) -> void:
	_mode = mode
	var editable := (mode == PianoRoll.Mode.EDITING)
	for slider in _sliders:
		if is_instance_valid(slider):
			slider.mouse_filter = Control.MOUSE_FILTER_STOP if editable else Control.MOUSE_FILTER_IGNORE


func update_view(view_offset: float, zoom_level: float, pps: float, duration: float) -> void:
	_view_offset = view_offset
	_zoom_level = zoom_level
	_pps = pps
	_duration = duration
	if not _rebuild_pending:
		_rebuild_pending = true
		call_deferred("_deferred_reposition")


func _deferred_reposition() -> void:
	_rebuild_pending = false
	_reposition_sliders()


func clear_sliders() -> void:
	for slider in _sliders:
		if is_instance_valid(slider):
			slider.queue_free()
	_sliders.clear()
	_slider_note_indices.clear()


# ─── 内部方法 ─────────────────────────────────────────────

func _rebuild_sliders() -> void:
	clear_sliders()
	if _notes.is_empty():
		return
	var editable := (_mode == PianoRoll.Mode.EDITING)
	for i in range(_notes.size()):
		var note: PianoRoll.RollNote = _notes[i]
		if note.channel != active_channel:
			continue
		var slider := VSlider.new()
		slider.min_value = 1
		slider.max_value = 127
		slider.step = 1
		slider.value = note.velocity
		slider.scrollable = false
		slider.size_flags_vertical = Control.SIZE_EXPAND_FILL
		slider.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		slider.mouse_filter = Control.MOUSE_FILTER_STOP if editable else Control.MOUSE_FILTER_IGNORE
		# 轨道：用 grabber_area 样式让填充部分更明显
		var base_color := ChannelColors.COLORS[note.channel % 16]
		var track_sb := StyleBoxFlat.new()
		track_sb.bg_color = base_color * 0.3
		track_sb.set_content_margin_all(2)
		track_sb.set_corner_radius_all(2)
		slider.add_theme_stylebox_override("slider", track_sb)
		var note_idx_for_slider := i
		slider.gui_input.connect(func(event: InputEvent) -> void:
			_on_slider_input(event, note_idx_for_slider, slider)
		)
		slider.mouse_entered.connect(func() -> void:
			note_hovered.emit(note_idx_for_slider)
		)
		slider.mouse_exited.connect(func() -> void:
			note_hovered.emit(-1)
		)
		add_child(slider)
		_sliders.append(slider)
		_slider_note_indices.append(i)
	_reposition_sliders()
	_update_selection_highlight()


const _STACK_GAP: float = 2.0  ## 重叠 slider 之间的间距像素

func _reposition_sliders() -> void:
	if size.x <= _LABEL_WIDTH:
		return
	var epps := _pps * _zoom_level
	# 计算每个 slider 的基础位置和宽度
	var rects: Array[Dictionary] = []
	for j in range(_sliders.size()):
		var note_idx: int = _slider_note_indices[j]
		var note: PianoRoll.RollNote = _notes[note_idx]
		var x := (note.start_time - _view_offset) * epps + _LABEL_WIDTH
		var w := note.duration * epps
		rects.append({"x": x, "w": w, "end": x + w})
	# 为每个 slider 分配列号（同一组重叠的 slider 获得不同列号）
	var columns: Array[int] = []
	columns.resize(rects.size())
	for j in range(rects.size()):
		var col := 0
		var used_cols: Dictionary = {}
		for k in range(j):
			if rects[j]["x"] < rects[k]["end"] and rects[j]["end"] > rects[k]["x"]:
				used_cols[columns[k]] = true
		while used_cols.has(col):
			col += 1
		columns[j] = col
	# 计算每组重叠区域的列数，等分宽度
	var slot_x: Array[float] = []
	var slot_w: Array[float] = []
	for j in range(rects.size()):
		# 找到与 j 重叠的最大列号
		var max_col := columns[j]
		for k in range(j + 1, rects.size()):
			if rects[j]["x"] < rects[k]["end"] and rects[j]["end"] > rects[k]["x"]:
				max_col = maxi(max_col, columns[k])
		var total_cols := max_col + 1
		var col_w: float = (rects[j]["w"] - _STACK_GAP * float(total_cols - 1)) / float(total_cols)
		slot_x.append(rects[j]["x"] + columns[j] * (col_w + _STACK_GAP))
		slot_w.append(maxf(col_w, 4.0))
	# 应用位置
	for j in range(_sliders.size()):
		var slider: VSlider = _sliders[j]
		if not is_instance_valid(slider):
			continue
		if rects[j]["end"] < _LABEL_WIDTH or rects[j]["x"] > size.x:
			slider.visible = false
			continue
		slider.visible = true
		slider.set_position(Vector2(slot_x[j], 0.0))
		slider.set_size(Vector2(slot_w[j], size.y))


func _update_selection_highlight() -> void:
	var sel_set: Dictionary = {}
	for idx in _selection:
		sel_set[idx] = true
	for j in range(_sliders.size()):
		var slider: VSlider = _sliders[j]
		if not is_instance_valid(slider):
			continue
		var note_idx: int = _slider_note_indices[j]
		if sel_set.has(note_idx):
			slider.modulate = Color(1, 1, 1, 1.0)
		else:
			slider.modulate = Color(0.7, 0.7, 0.7, 1.0)


func _on_slider_input(event: InputEvent, note_index: int, slider: VSlider) -> void:
	if _mode != PianoRoll.Mode.EDITING:
		return
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed:
			_dragging_slider_idx = note_index
			_drag_original_velocity = _notes[note_index].velocity if note_index >= 0 and note_index < _notes.size() else 0
		elif mb.button_index == MOUSE_BUTTON_LEFT and not mb.pressed:
			if _dragging_slider_idx == note_index and note_index >= 0 and note_index < _notes.size():
				var new_vel := int(slider.value)
				if new_vel != _drag_original_velocity:
					velocity_changed.emit(note_index, new_vel)
			_dragging_slider_idx = -1


func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED:
		_reposition_sliders()
