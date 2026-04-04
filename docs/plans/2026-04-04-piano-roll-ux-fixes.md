# Piano Roll UX 修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 Piano Roll 的 4 个 UX 问题，使编辑操作可用。

**Architecture:** 纯 GDScript 修改，仅涉及 `piano_roll.gd`。

**Tech Stack:** GDScript, Godot 4.6

---

## 问题分析

| # | 问题 | 根因 |
|---|------|------|
| 1 | 鼠标进入 Piano Roll 变成输入光标 | `_ready()` 硬编码 `CURSOR_IBEAM` |
| 2 | Ctrl+Z 撤销/重做无效果 | 键盘事件在 `_gui_input` 中处理，但 PianoRoll 从未获取焦点，事件无法到达 |
| 3 | 右键菜单位置不对 | `get_global_mouse_position()` 返回视口坐标，但 `popup()` 的 `position` 是父节点局部坐标 |
| 4 | 多选需要 Ctrl+click，应改为拖拽框选 | 缺少矩形框选功能 |

---

### Task 1：修复光标样式

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:167`

**Step 1: 修改 _ready() 中的光标**

```gdscript
# 旧：
mouse_default_cursor_shape = Control.CURSOR_IBEAM
# 新：
mouse_default_cursor_shape = Control.CURSOR_ARROW
```

**Step 2: 验证**

重启编辑器，鼠标进入 Piano Roll 应为箭头。

---

### Task 2：修复 Ctrl+Z / Ctrl+Shift+Z 快捷键

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**根因：** `_gui_input()` 仅在 Control 拥有焦点时接收键盘事件。PianoRoll 从未调用 `grab_focus()`，所以 Ctrl+Z 事件无法到达。

**Step 1: 将键盘快捷键从 `_gui_input` 移到 `_unhandled_key_input`**

从 `_gui_input` 中**删除**整个 `if event is InputEventKey:` 块（原 319-338 行）。

新增独立方法：

```gdscript
func _unhandled_key_input(event: InputEvent) -> void:
	if not _editing:
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
	if key.keycode == KEY_DELETE and not _selection.is_empty():
		get_viewport().set_input_as_handled()
		_delete_selected()
		return
```

**Step 2: 验证**

编辑模式下移动/删除音符后按 Ctrl+Z 应恢复。

---

### Task 3：修复右键菜单位置

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**根因：** `get_global_mouse_position()` 返回视口全局坐标，但 `_context_menu`（PianoRoll 子节点）的 `position` 是相对父节点的局部坐标。需要坐标转换。

**Step 1: 修正 popup 定位**

```gdscript
# 旧：
_context_menu.position = get_global_mouse_position() + Vector2(2, 2)
_context_menu.popup()

# 新：
_context_menu.position = get_global_mouse_position() - global_position + Vector2(2, 2)
_context_menu.popup()
```

**Step 2: 验证**

右键点击音符，菜单应出现在鼠标旁边。

---

### Task 4：实现拖拽框选

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: 添加框选状态变量**

在拖拽状态区域添加：

```gdscript
## 框选状态
var _box_selecting: bool = false
var _box_select_start: Vector2 = Vector2.ZERO
var _box_select_end: Vector2 = Vector2.ZERO
```

**Step 2: 修改 _gui_input 中左键点击空白处的逻辑**

将"点击空白取消选中 + seek"改为"开始框选"：

```gdscript
# 原逻辑（点击空白）：
# _selection.clear()
# queue_redraw()
# seek ...

# 新逻辑（编辑模式下点击空白开始框选）：
else:
	if _editing:
		_selection.clear()
		_box_selecting = true
		_box_select_start = mb.position
		_box_select_end = mb.position
		queue_redraw()
	else:
		_selection.clear()
		queue_redraw()
		var t := _pixel_to_time(mb.position.x)
		if _duration > 0.0 and t >= 0.0 and t <= _duration:
			seek_requested.emit(t)
```

**Step 3: 修改 mouse motion 处理框选拖拽**

在 `InputEventMouseMotion` 处理中，拖拽检测之前加入框选更新：

```gdscript
if event is InputEventMouseMotion:
	if _box_selecting:
		_box_select_end = event.position
		queue_redraw()
	elif _dragging:
		# ... 原有拖拽逻辑
```

**Step 4: 修改 mouse up 完成框选**

在 `_gui_input` 的 mouse up 处理中（非拖拽、非右键），增加框选完成逻辑。新增 `elif` 分支：

```gdscript
elif _box_selecting:
	_box_selecting = false
	# 计算框选矩形（标准化，确保 min/max）
	var rect := Rect2(
		minf(_box_select_start.x, _box_select_end.x),
		minf(_box_select_start.y, _box_select_end.y),
		absf(_box_select_end.x - _box_select_start.x),
		absf(_box_select_end.y - _box_select_start.y)
	)
	if rect.size.x > 2.0 and rect.size.y > 2.0:
		for i in _notes.size():
			var n := _notes[i]
			if _muted_channels.has(n.channel):
				continue
			var nx := _time_to_x(n.start_time)
			var nw := n.duration * _pixels_per_second
			var ny := _pitch_to_y(n.pitch + 1)
			var nh := _pixels_per_note
			if rect.intersects(Rect2(nx, ny, nw, nh)):
				if not _selection.has(i):
					_selection.append(i)
	queue_redraw()
```

**Step 5: 在 _draw 中绘制框选矩形**

在 `_draw()` 末尾，`_draw_annotations()` 之后添加：

```gdscript
# 框选矩形
if _box_selecting:
	var rect := Rect2(
		minf(_box_select_start.x, _box_select_end.x),
		minf(_box_select_start.y, _box_select_end.y),
		absf(_box_select_end.x - _box_select_start.x),
		absf(_box_select_end.y - _box_select_start.y)
	)
	draw_rect(rect, Color(1, 1, 1, 0.15))
	draw_rect(rect, Color(1, 1, 1, 0.6), false, 1.0)
```

**Step 6: 移除 Ctrl+click 多选逻辑**

从左键点击音符的处理中删除 `if mb.ctrl_pressed:` 分支，改为直接选中（替换原有多选逻辑）：

```gdscript
if hit["index"] >= 0:
	if mb.shift_pressed:
		# Shift 保持多选能力（点击追加选中）
		var idx: int = hit["index"]
		var found := _selection.find(idx)
		if found >= 0:
			_selection.remove_at(found)
		else:
			_selection.append(idx)
	else:
		_selection.clear()
		_selection.append(hit["index"])
	# ... 拖拽开始逻辑
```

**Step 7: 验证**

编辑模式下空白处拖拽 → 半透明白色框 → 松开 → 框内音符全部选中。

---

## 注意事项

- Task 1-3 是独立修复，可分别验收
- Task 4（框选）改动最大，涉及 `_gui_input` 的 mouse down/move/up 三个分支
- `_unhandled_key_input` 需要 PianoRoll 在场景树中才能工作（已满足）
- 框选应只在编辑模式下启用，非编辑模式下点击空白仍触发 seek
