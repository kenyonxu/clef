# Velocity Lane 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Piano Roll 底部添加可折叠的 Velocity Lane 面板，用 VSlider 可视化编辑每个音符的力度值。

**Architecture:** 创建独立的 `VelocityLane` 控件（extends Control），通过信号与 PianoRoll 双向同步。在 ClefStation 的 center_vbox 中插入到 PianoRoll 与 MiniMixer 之间，配一个折叠按钮。

**Tech Stack:** GDScript (Godot 4), VSlider 控件, 信号系统

**Spec:** `docs/superpowers/specs/2026-04-07-velocity-lane-design.md`

---

### Task 1: PianoRoll 新增 selection_changed 信号

当前 PianoRoll 的 `_selection` 变化时没有发射信号，VelocityLane 需要监听此变化来高亮对应 slider。

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd` (signal declarations + emission points)

- [ ] **Step 1: 添加信号声明**

在 `piano_roll.gd` 约第 38 行（`track_changed` 信号之后）添加：

```gdscript
## 选中状态变更（给 VelocityLane 用）
signal selection_changed(indices: Array[int])
```

- [ ] **Step 2: 在所有修改 _selection 的位置发射信号**

需要搜索所有修改 `_selection` 的代码路径，在其后添加 `selection_changed.emit(_selection)`。关键位置：

1. `_handle_mouse_button` 中单击选中/多选/取消选中后
2. `_handle_mouse_button` 中双击创建音符后
3. `_drag_update` 中 MOVE/RESIZE 结束后（`_gui_input` 的 InputEventMouseButton released 分支）
4. `clear_notes()` 中 `_selection.clear()` 后
5. `set_notes()` 中 `_selection.clear()` 后
6. `_shortcut_input` 中 Ctrl+A 全选后
7. 粘贴操作（Ctrl+V）后
8. 删除操作（Delete key）后

在每个 `_selection` 修改完成后添加：
```gdscript
selection_changed.emit(_selection)
```

注意：`_selection.clear()` 后也要 emit（空数组表示无选中）。

- [ ] **Step 3: 在 Godot 编辑器中验证**

打开 ClefStation，加载 MIDI 文件，切换编辑模式，点击音符、Ctrl+A、Delete，确认编辑器控制台无报错。

- [ ] **Step 4: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add selection_changed signal"
```

---

### Task 2: 创建 VelocityLane 控件骨架

**Files:**
- Create: `addons/clef/editor/piano_roll/velocity_lane.gd`

- [ ] **Step 1: 创建 VelocityLane 控件文件**

```gdscript
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
```

- [ ] **Step 2: Commit**

```bash
git add addons/clef/editor/piano_roll/velocity_lane.gd
git commit -m "feat(piano-roll): add VelocityLane control skeleton"
```

---

### Task 3: 在 ClefStation 中集成 VelocityLane

**Files:**
- Modify: `addons/clef/editor/clef_station.gd`

- [ ] **Step 1: 添加成员变量**

在 `clef_station.gd` 中 `_piano_roll` 声明附近添加：

```gdscript
var _velocity_lane: VelocityLane
var _velocity_toggle: Button
```

- [ ] **Step 2: 在 center_vbox 中创建 VelocityLane 和折叠按钮**

在 `clef_station.gd` 约第 270 行（`center_vbox.add_child(_piano_roll)` 之后，`_mini_mixer` 之前）添加：

```gdscript
	# ── Velocity Lane ──
	_velocity_toggle = Button.new()
	_velocity_toggle.text = "▼ " + l10n.t("Velocity")
	_velocity_toggle.flat = true
	_velocity_toggle.custom_minimum_size = Vector2i(0, 24)
	_velocity_toggle.pressed.connect(func() -> void:
		_velocity_lane.visible = not _velocity_lane.visible
		_velocity_toggle.text = ("▼ " if _velocity_lane.visible else "▶ ") + l10n.t("Velocity")
	)
	center_vbox.add_child(_velocity_toggle)

	_velocity_lane = VelocityLane.new()
	_velocity_lane.custom_minimum_size = Vector2i(0, 80)
	_velocity_lane.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	center_vbox.add_child(_velocity_lane)

	# VelocityLane → PianoRoll: 通知 velocity 变更
	_velocity_lane.velocity_changed.connect(func(note_index: int, new_velocity: int) -> void:
		_on_velocity_changed(note_index, new_velocity)
	)
```

- [ ] **Step 3: 连接 PianoRoll 信号到 VelocityLane**

在现有信号连接区域（约第 266-267 行 `_piano_roll.view_offset_changed.connect` 附近）添加：

```gdscript
	_piano_roll.selection_changed.connect(_velocity_lane.set_selection)
	_piano_roll.note_edited.connect(func() -> void:
		_velocity_lane.set_notes(_piano_roll.get_notes())
	)
	_piano_roll.track_changed.connect(func(ch: int, _preset: int) -> void:
		_velocity_lane.set_active_channel(ch)
	)
	_piano_roll.view_offset_changed.connect(func(vo: float, zl: float, pps: float, dur: float) -> void:
		_velocity_lane.update_view(vo, zl, pps, dur)
	)
```

- [ ] **Step 4: 添加 _on_velocity_changed 回调**

在 ClefStation 中添加方法：

```gdscript
func _on_velocity_changed(note_index: int, new_velocity: int) -> void:
	var notes := _piano_roll.get_notes()
	if note_index >= 0 and note_index < notes.size():
		notes[note_index].velocity = new_velocity
		_piano_roll.queue_redraw()
		_edit_dirty = true
```

- [ ] **Step 5: 在 _update_piano_roll 中同步 VelocityLane**

在 `_update_piano_roll()` 方法中（调用 `_piano_roll.set_notes(...)` 之后）添加：

```gdscript
	_velocity_lane.set_notes(_piano_roll.get_notes())
```

- [ ] **Step 6: Commit**

```bash
git add addons/clef/editor/clef_station.gd
git commit -m "feat(piano-roll): integrate VelocityLane into ClefStation"
```

---

### Task 4: 为 VelocityLane slider 添加 Undo/Redo 支持

当前 `_on_slider_changed` 直接修改 velocity 但没有 undo 快照。需要在 PianoRoll 侧处理 undo。

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`
- Modify: `addons/clef/editor/clef_station.gd`

- [ ] **Step 1: 在 PianoRoll 中添加公开方法用于外部 velocity 修改**

在 `piano_roll.gd` 中添加：

```gdscript
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
```

- [ ] **Step 2: 修改 ClefStation 的 _on_velocity_changed 调用此方法**

将 Task 3 中的 `_on_velocity_changed` 替换为：

```gdscript
func _on_velocity_changed(note_index: int, new_velocity: int) -> void:
	_piano_roll.set_note_velocity(note_index, new_velocity)
```

- [ ] **Step 3: 验证 undo/redo**

在 Godot 编辑器中：加载 MIDI → 打开 Velocity Lane → 拖拽 slider 改变 velocity → Ctrl+Z 撤销 → Ctrl+Y 重做，确认 velocity 值正确恢复。

- [ ] **Step 4: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd addons/clef/editor/clef_station.gd
git commit -m "feat(piano-roll): add undo/redo support for velocity slider changes"
```

---

### Task 5: VSlider 样式与绘制优化

**Files:**
- Modify: `addons/clef/editor/piano_roll/velocity_lane.gd`

- [ ] **Step 1: 添加 _draw 方法绘制刻度标签和背景**

在 VelocityLane 中重写 `_draw`：

```gdscript
func _draw() -> void:
	# 背景
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.08, 0.08, 0.12))
	# 刻度标签
	var font := ThemeDB.fallback_font
	draw_string(font, Vector2(2, 14), "127", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color(0.35, 0.35, 0.4))
	draw_string(font, Vector2(2, size.y / 2.0 + 4), "64", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color(0.35, 0.35, 0.4))
	draw_string(font, Vector2(2, size.y - 2), "0", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color(0.35, 0.35, 0.4))
	# 中间参考线
	draw_line(Vector2(_LABEL_WIDTH, size.y / 2.0), Vector2(size.x, size.y / 2.0), Color(0.2, 0.2, 0.28), 1.0, true)
```

- [ ] **Step 2: 在 _rebuild_sliders 中设置 slider 颜色**

在创建 slider 时（`VSlider.new()` 之后）添加颜色设置，使用通道颜色：

```gdscript
		var base_color := ChannelColors.COLORS[note.channel % 16]
		var stylebox := StyleBoxFlat.new()
		stylebox.bg_color = base_color
		stylebox.set_corner_radius_all(2)
		slider.add_theme_stylebox_override("slider", stylebox)
```

- [ ] **Step 3: 验证视觉效果**

在 Godot 编辑器中加载 MIDI，确认 Velocity Lane 显示：深色背景、刻度标签、颜色与通道一致、slider 拖拽手感正常。

- [ ] **Step 4: Commit**

```bash
git add addons/clef/editor/piano_roll/velocity_lane.gd
git commit -m "feat(piano-roll): add VelocityLane visual styling and labels"
```

---

### Task 6: scroll 同步优化

当前 `_reposition_sliders` 在每次 view 变化时全量重建位置。需要确保与 PianoRoll 的水平滚动条同步。

**Files:**
- Modify: `addons/clef/editor/piano_roll/velocity_lane.gd`

- [ ] **Step 1: 防抖 rebuild**

修改 `update_view` 方法，使用 deferred 调用避免高频重建：

```gdscript
var _rebuild_pending: bool = false

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
```

- [ ] **Step 2: 验证滚动同步**

加载长 MIDI 文件，水平滚动 PianoRoll，确认 Velocity Lane 的 slider 同步移动且无卡顿。

- [ ] **Step 3: Commit**

```bash
git add addons/clef/editor/piano_roll/velocity_lane.gd
git commit -m "perf(piano-roll): debounce VelocityLane rebuild on scroll"
```

---

### Task 7: i18n 支持

**Files:**
- Modify: `addons/clef/editor/piano_roll/velocity_lane.gd` (如果需要 l10n)
- Modify: i18n 文件（如有）

- [ ] **Step 1: 检查现有 i18n 机制**

查看 `ClefL10n` 的使用方式，确认 "Velocity" 翻译是否已存在。如果不存在，在翻译文件中添加。

- [ ] **Step 2: Commit**

```bash
git add addons/clef/editor/piano_roll/velocity_lane.gd
git commit -m "feat(piano-roll): add i18n for Velocity Lane"
```
