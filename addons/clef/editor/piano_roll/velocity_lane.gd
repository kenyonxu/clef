## Velocity Lane — 音符力度可视化编辑面板
@tool
class_name VelocityLane
extends Control


signal velocity_changed(note_index: int, new_velocity: int)


## 活动通道
var active_channel: int = 0
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
var _pps: float = 100.0  ## pixels per second
var _duration: float = 0.0
## 左侧刻度区域宽度
const _LABEL_WIDTH: float = 32.0


func _ready() -> void:
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
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


## 清空所有 slider
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
	for i in range(_notes.size()):
		var note: PianoRoll.RollNote = _notes[i]
		if note.channel != active_channel:
			continue
		var slider := VSlider.new()
		slider.min_value = 1
		slider.max_value = 127
		slider.step = 1
		slider.value = note.velocity
		slider.custom_minimum_size = Vector2i(4, 0)
		slider.size_flags_vertical = Control.SIZE_EXPAND_FILL
		slider.scrollable = false
		var base_color := ChannelColors.COLORS[note.channel % 16]
		var stylebox := StyleBoxFlat.new()
		stylebox.bg_color = base_color
		stylebox.set_corner_radius_all(2)
		slider.add_theme_stylebox_override("slider", stylebox)
		var note_idx_for_slider := i
		slider.gui_input.connect(func(event: InputEvent) -> void:
			_on_slider_input(event, note_idx_for_slider, slider)
		)
		add_child(slider)
		_sliders.append(slider)
		_slider_note_indices.append(i)
	_reposition_sliders()
	_update_selection_highlight()


func _reposition_sliders() -> void:
	var visible_width := size.x - _LABEL_WIDTH
	if visible_width <= 0:
		return
	for j in range(_sliders.size()):
		var slider: VSlider = _sliders[j]
		if not is_instance_valid(slider):
			continue
		var note_idx: int = _slider_note_indices[j]
		var note: PianoRoll.RollNote = _notes[note_idx]
		var x := (note.start_time - _view_offset) * _pps + _LABEL_WIDTH
		var w := note.duration * _pps
		# 超出可见区域则隐藏
		if x + w < _LABEL_WIDTH or x > size.x:
			slider.visible = false
			continue
		slider.visible = true
		slider.position.x = x
		slider.size.x = maxf(w, 4)
		slider.size.y = size.y


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
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed:
			# Drag start
			_dragging_slider_idx = note_index
			_drag_original_velocity = _notes[note_index].velocity if note_index >= 0 and note_index < _notes.size() else 0
		elif mb.button_index == MOUSE_BUTTON_LEFT and not mb.pressed:
			# Drag end — emit velocity change
			if _dragging_slider_idx == note_index and note_index >= 0 and note_index < _notes.size():
				var new_vel := int(slider.value)
				if new_vel != _drag_original_velocity:
					velocity_changed.emit(note_index, new_vel)
			_dragging_slider_idx = -1


func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED:
		_reposition_sliders()
