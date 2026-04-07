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
		var idx := i  # 捕获当前索引
		slider.value_changed.connect(func(val: float) -> void:
			_on_slider_changed(idx, int(val))
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


func _on_slider_changed(note_index: int, new_velocity: int) -> void:
	if note_index >= 0 and note_index < _notes.size():
		_notes[note_index].velocity = new_velocity
	velocity_changed.emit(note_index, new_velocity)


func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED:
		_reposition_sliders()
