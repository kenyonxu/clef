# Piano Roll 可操作编辑 — 分阶段实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将现有 PianoRoll 从只读可视化升级为可操作的审查微调工具，支持选中/移动/删除音符、撤销重做、标注审查、临时音符试听，以及导出修改后的 MIDI。

**Architecture:** 原地升级现有 `PianoRoll` Control。渲染层（`_draw`）只读数据、画完即结束；交互层通过信号通知修改数据、触发 `queue_redraw()`。新增 `EditCommand` 撤销/重做框架包裹所有编辑操作。ClefStation 通过公共 API 和新增信号通信。

**Tech Stack:** GDScript, Godot 4.6, Control._draw() API, PopupMenu, MidiWriter

**设计文档：** [2026-04-02-piano-roll-interactive-design.md](2026-04-02-piano-roll-interactive-design.md)

**前置依赖：** [2026-03-30-piano-roll-implementation.md](2026-03-30-piano-roll-implementation.md)（只读可视化已实现，`piano_roll.gd` 312 行）

---

## 阶段间依赖关系

```
Phase 1: 撤销/重做框架 + 选中系统
    ↓ 所有后续编辑操作都通过 EditCommand 包裹
Phase 2: 音符编辑操作（移动/删除/音高调整）
    ↓ Phase 2 产出可编辑的音符数据
Phase 3: 右键菜单 + MIDI 导出
    ↓ Phase 3 产出完整的编辑→导出闭环
Phase 4: 标注与审查系统
    ↓ Phase 4 在 Phase 3 闭环上叠加审查标记
Phase 5: 临时音符与屏蔽
    ↓ Phase 5 的导出合并依赖 Phase 3 的导出管线
Phase 6: ABC 导出
    ↓ Phase 6 的输入来自 Phase 3/5 导出的 MIDI 文件
```

---

## Phase 1: 撤销/重做框架 + 选中系统

**验收标准：** 选中音符高亮显示，Ctrl+Z/Ctrl+Shift+Z 撤销重做操作可正确恢复状态。

### Task 1.1: EditCommand 类 + 撤销/重做栈

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:12-24`（在 RollNote 类之后新增 EditCommand）

**Step 1: 在 RollNote 类后添加 EditCommand 内部类**

在 `piano_roll.gd` 第 24 行之后（RollNote 类结束后）添加：

```gdscript
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
```

**Step 2: 在 `_notes` 变量区域（第 70 行之后）添加撤销/重做状态字段**

```gdscript
## 撤销/重做栈
var _undo_stack: Array[EditCommand] = []
var _redo_stack: Array[EditCommand] = []
const MAX_HISTORY: int = 100
```

**Step 3: 添加撤销/重做方法**

在文件末尾（`_draw_playback_cursor` 之后）添加：

```gdscript
# ─── 撤销/重做 ─────────────────────────────────────────────

func begin_command(type: String, description: String) -> EditCommand:
	return EditCommand.new(type, description)

func commit_command(cmd: EditCommand) -> void:
	_undo_stack.append(cmd)
	if _undo_stack.size() > MAX_HISTORY:
		_undo_stack.pop_front()
	_redo_stack.clear()
	queue_redraw()
	note_edited.emit()

func _undo() -> void:
	if _undo_stack.is_empty():
		return
	var cmd := _undo_stack.pop_back() as EditCommand
	_apply_snapshot(cmd.before)
	_redo_stack.append(cmd)
	queue_redraw()
	note_edited.emit()

func _redo() -> void:
	if _redo_stack.is_empty():
		return
	var cmd := _redo_stack.pop_back() as EditCommand
	_apply_snapshot(cmd.after)
	_undo_stack.append(cmd)
	queue_redraw()
	note_edited.emit()

func _apply_snapshot(snapshot: Dictionary) -> void:
	# 各操作类型在 Phase 2/3 实现具体恢复逻辑
	# 目前仅处理 delete/restore
	if snapshot.has("deleted_note"):
		_notes.insert(snapshot["index"], snapshot["deleted_note"])
	elif snapshot.has("added_index"):
		_notes.remove_at(snapshot["added_index"])
	elif snapshot.has("index") and snapshot.has("note_data"):
		var idx: int = snapshot["index"]
		if idx >= 0 and idx < _notes.size():
			_notes[idx] = snapshot["note_data"]
```

**Step 4: 添加新信号**

在第 9 行 `signal seek_requested` 之后添加：

```gdscript
## 音符被修改（触发导出脏标记）
signal note_edited()
```

**Step 5: 在 `_gui_input` 中绑定 Ctrl+Z / Ctrl+Shift+Z**

修改 `_gui_input` 方法（第 204 行），在现有 `InputEventMouseButton` 处理之前添加键盘处理：

```gdscript
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
		# ... 现有代码不变 ...
```

**Step 6: 手动验证**

运行 Godot 编辑器，加载一个 MIDI 文件，打开 Piano Roll：
- 按 Ctrl+Z（应无报错，栈为空）
- 按 Ctrl+Shift+Z（应无报错，栈为空）
- 检查 `note_edited` 信号连接正常（ClefStation 侧暂不需要处理）

**Step 7: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add EditCommand undo/redo framework"
```

### Task 1.2: 选中系统

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: 添加选中状态字段**

在编辑状态区域（Task 1.1 添加的 `_redo_stack` 之后）添加：

```gdscript
## 选中音符索引集合
var _selection: Array[int] = []

## 鼠标悬停音符索引（-1 表示无）
var _hovered_note: int = -1
```

**Step 2: 添加命中检测方法**

```gdscript
## 命中检测：返回 {index: int, edge: String}
## edge: "none" | "left" | "right"（容差 4px）
func _hit_test(pos: Vector2) -> Dictionary:
	var time := _pixel_to_time(pos.x)
	var pitch := _y_to_pitch(pos.y)
	for i in range(_notes.size() - 1, -1, -1):  # 后绘制的优先
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
```

**Step 3: 修改 `_gui_input` 处理鼠标选中**

在 `InputEventMouseButton` 分支中，区分左键点击：

```gdscript
func _gui_input(event: InputEvent) -> void:
	# ... Ctrl+Z / Ctrl+Shift+Z 键盘处理不变 ...

	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed:
			var hit := _hit_test(mb.position)
			if hit["index"] >= 0:
				# Ctrl 多选 / 单选
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
				# 点击空白取消选中
				_selection.clear()
				queue_redraw()
		elif mb.button_index == MOUSE_BUTTON_LEFT and not mb.pressed:
			pass  # mouse up — 拖拽结束在 Phase 2 处理
		elif mb.button_index == MOUSE_BUTTON_RIGHT:
			# Phase 3 处理右键菜单
			pass

	if event is InputEventMouseMotion:
		var hit := _hit_test(event.position)
		if hit["index"] != _hovered_note:
			_hovered_note = hit["index"]
			queue_redraw()
```

**注意：** 原有的 `seek_requested` 左键点击逻辑保留。当点击空白区域（`hit["index"] < 0`）且不在音符上时，同时触发 seek。修改为：

```gdscript
if hit["index"] >= 0:
	# 选中逻辑...
else:
	_selection.clear()
	queue_redraw()
	# 原有 seek 逻辑：点击空白跳转播放位置
	var t := _pixel_to_time(mb.position.x)
	if _duration > 0.0 and t >= 0.0 and t <= _duration:
		seek_requested.emit(t)
```

**Step 4: 修改 `_draw_notes` 渲染选中高亮**

在 `_draw_notes` 中绘制完音符矩形后，检查选中态：

```gdscript
func _draw_notes() -> void:
	# 先收集选中索引到 Dictionary 以便 O(1) 查找
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
```

**Step 5: 手动验证**

运行 Godot 编辑器，加载 MIDI：
- 点击音符 → 高亮白色边框出现
- Ctrl+点击第二个音符 → 两个都高亮
- 点击空白区域 → 选中清空，播放头跳转
- 鼠标悬停音符 → 淡白叠加

**Step 6: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add note selection system with hit detection"
```

---

## Phase 2: 音符编辑操作

**验收标准：** 可以拖拽移动音符（音高/时间）、拖拽边缘调整时长、Delete 键删除音符、所有操作均可撤销重做。

**前置：** Phase 1 的 EditCommand 框架 + 选中系统。

### Task 2.1: 音符移动（拖拽改音高/时间）

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: 添加拖拽状态字段**

```gdscript
## 拖拽状态
var _dragging: bool = false
var _drag_type: int = 0  ## 0=NONE, 1=MOVE, 2=RESIZE_LEFT, 3=RESIZE_RIGHT
var _drag_start_pos: Vector2 = Vector2.ZERO
var _drag_original_notes: Array[Dictionary] = []  ## 拖拽前快照 [{index, pitch, start_time, duration}]
```

**Step 2: 在 `_gui_input` 中处理左键按下开始拖拽**

```gdscript
# 在左键按下分支中，选中后检查是否命中边缘
if hit["index"] >= 0:
	# ... 选中逻辑不变 ...
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
	# 快照所有选中音符
	for idx in _selection:
		var n := _notes[idx]
		_drag_original_notes.append({
			"index": idx,
			"pitch": n.pitch,
			"start_time": n.start_time,
			"duration": n.duration
		})
```

**Step 3: 处理鼠标移动拖拽**

在 `InputEventMouseMotion` 分支中：

```gdscript
if event is InputEventMouseMotion and _dragging:
	var delta := event.position - _drag_start_pos
	match _drag_type:
		1:  # MOVE
			var pitch_delta := int(delta.y / _pixels_per_note)
			var time_delta := delta.x / _pixels_per_second
			for orig in _drag_original_notes:
				var idx: int = orig["index"]
				if idx < _notes.size():
					_notes[idx].pitch = orig["pitch"] - pitch_delta
					_notes[idx].start_time = orig["start_time"] + time_delta
			queue_redraw()
		2:  # RESIZE_LEFT（调整 start_time 和 duration）
			var time_delta := delta.x / _pixels_per_second
			for orig in _drag_original_notes:
				var idx: int = orig["index"]
				if idx < _notes.size():
					_notes[idx].start_time = orig["start_time"] + time_delta
					_notes[idx].duration = orig["duration"] - time_delta
			queue_redraw()
		3:  # RESIZE_RIGHT（调整 duration）
			var time_delta := delta.x / _pixels_per_second
			for orig in _drag_original_notes:
				var idx: int = orig["index"]
				if idx < _notes.size():
					_notes[idx].duration = orig["duration"] + time_delta
			queue_redraw()
```

**Step 4: 处理鼠标释放结束拖拽 + commit command**

在 `InputEventMouseButton` 的 `not mb.pressed` 分支中：

```gdscript
elif mb.button_index == MOUSE_BUTTON_LEFT and not mb.pressed and _dragging:
	_dragging = false
	# 检查是否有实际变化
	var changed := false
	for orig in _drag_original_notes:
		var idx: int = orig["index"]
		if idx < _notes.size():
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
			if idx < _notes.size():
				after_snap.append({
					"index": idx,
					"pitch": _notes[idx].pitch,
					"start_time": _notes[idx].start_time,
					"duration": _notes[idx].duration
				})
		cmd.after = {"indices": after_snap}
		commit_command(cmd)
	_drag_type = 0
	_drag_original_notes.clear()
```

**Step 5: 完善 `_apply_snapshot` 处理 move/resize**

在 Task 1.1 的 `_apply_snapshot` 中追加：

```gdscript
elif snapshot.has("indices"):
	## move / resize 批量恢复
	var indices: Array = snapshot["indices"]
	for item in indices:
		var idx: int = item["index"]
		if idx >= 0 and idx < _notes.size():
			_notes[idx].pitch = item["pitch"]
			_notes[idx].start_time = item["start_time"]
			_notes[idx].duration = item["duration"]
```

**Step 6: 手动验证**

加载 MIDI，选中音符：
- 垂直拖拽 → 音高变化，松开后 Ctrl+Z 恢复
- 水平拖拽 → 时间位置变化
- 拖拽右边缘 → 时长变化
- 多选后拖拽 → 所有选中音符同步移动

**Step 7: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add note drag to move pitch/time/duration"
```

### Task 2.2: Delete 键删除选中音符

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: 在 `_gui_input` 的键盘分支中添加 Delete 键处理**

在 Ctrl+Y 之后添加：

```gdscript
if key.keycode == KEY_DELETE and not _selection.is_empty():
	get_viewport().set_input_as_handled()
	_delete_selected()
	return
```

**Step 2: 实现 `_delete_selected` 方法**

```gdscript
func _delete_selected() -> void:
	if _selection.is_empty():
		return
	# 按索引降序排列，从后往前删避免索引偏移
	var sorted := _selection.duplicate()
	sorted.sort_custom(func(a, b): return a > b)

	var cmd := begin_command("delete", "删除 %d 个音符" % sorted.size())
	# before: 记录被删除的音符数据（按原始索引）
	var deleted_items := []
	for idx in sorted:
		deleted_items.append({"index": idx, "note_data": _notes[idx].duplicate()})
	cmd.before = {"deleted_items": deleted_items}

	for idx in sorted:
		_notes.remove_at(idx)

	cmd.after = {"deleted_indices": sorted.duplicate()}
	_selection.clear()
	commit_command(cmd)
```

**Step 3: 完善 `_apply_snapshot` 处理 delete**

在 `_apply_snapshot` 中追加：

```gdscript
elif snapshot.has("deleted_items"):
	## undo delete: 按原始索引恢复音符
	# before 快照中 index 是删除前的位置
	# 需要从后往前插入，恢复原始顺序
	var items: Array = snapshot["deleted_items"]
	# 按索引降序排列后从后往前插入
	var sorted_items := items.duplicate()
	sorted_items.sort_custom(func(a, b): return a["index"] > b["index"])
	for item in sorted_items:
		_notes.insert(item["index"], item["note_data"])
```

**Step 4: 手动验证**

选中 1-3 个音符，按 Delete：
- 音符从卷帘中消失
- Ctrl+Z → 音符恢复到原位
- Ctrl+Shift+Z → 再次删除

**Step 5: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add Delete key to remove selected notes"
```

---

## Phase 3: 右键菜单 + MIDI 导出

**验收标准：** 右键音符弹出上下文菜单（删除/改音高/编辑力度/导出 MIDI），导出按钮可用，修改后的 MIDI 文件写入 `addons/clef/output/`。

**前置：** Phase 2 的编辑操作已就绪，EditCommand 正确记录所有变更。

### Task 3.1: 右键上下文菜单

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`
- Modify: `addons/clef/editor/clef_station.gd`（连接新信号）

**Step 1: 添加右键菜单子节点**

在 `_ready()` 中创建 PopupMenu：

```gdscript
func _ready() -> void:
	# ... 现有 l10n 初始化 ...
	_create_context_menu()
	# ... 现有 return ...
```

新增方法：

```gdscript
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
	_context_menu.add_item("导出修改后的 MIDI", 10)
```

**Step 2: 添加字段和信号**

```gdscript
var _context_menu: PopupMenu

## 请求导出 MIDI
signal export_requested(notes: Array)
```

**Step 3: 在 `_gui_input` 中处理右键**

```gdscript
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
```

**Step 4: 实现菜单回调**

```gdscript
func _on_context_menu_item(id: int) -> void:
	match id:
		0:  # 删除
			_delete_selected()
		1:  # 音高 +1
			_shift_selected_pitch(1)
		2:  # 音高 -1
			_shift_selected_pitch(-1)
		3:  # 编辑力度
			_edit_velocity_popup()
		10:  # 导出 MIDI
			export_requested.emit(_get_edited_notes())
```

**Step 5: 实现辅助方法**

```gdscript
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
	# 使用 LineEdit 弹窗让用户输入力度值（0-127）
	# 简易实现：弹出 LineEdit Dialog
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
	# 预填当前选中音符的力度
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

var _velocity_dialog: AcceptDialog = null


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
```

**Step 6: 完善 `_apply_snapshot` 处理 property**

```gdscript
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
```

**Step 7: 添加获取编辑后音符的公共方法**

```gdscript
## 获取编辑后的音符数组（排除已删除的）
func get_notes() -> Array[RollNote]:
	return _notes.duplicate()
```

**Step 8: 手动验证**

- 右键音符 → 菜单弹出
- "删除音符" → 音符消失，Ctrl+Z 恢复
- "音高 +1/-1" → 音高变化
- "编辑力度" → 弹窗输入数值，确认后音符亮度变化

**Step 9: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add right-click context menu with edit actions"
```

### Task 3.2: MIDI 导出管线

**Files:**
- Modify: `addons/clef/editor/clef_station.gd`（连接 export_requested 信号）
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`（添加 `_get_edited_notes`）

**Step 1: 在 `piano_roll.gd` 中添加 `_get_edited_notes` 方法**

```gdscript
## 获取编辑后的音符（供导出使用）
func _get_edited_notes() -> Array[RollNote]:
	return _notes
```

**Step 2: 在 `clef_station.gd` 中连接 `export_requested` 信号**

在创建 PianoRoll 的代码之后（约第 173 行），添加信号连接：

```gdscript
_piano_roll.export_requested.connect(_on_piano_roll_export_requested)
```

**Step 3: 在 `clef_station.gd` 中实现导出回调**

```gdscript
func _on_piano_roll_export_requested(notes: Array) -> void:
	var midi_res: MidiResource = _editor_player.get_midi_resource()
	if midi_res == null:
		return
	# 构建 MidiData
	var midi_data := MidiData.new()
	midi_data.tempo = midi_res.tempo
	midi_data.timebase = midi_res.timebase
	# 收集每个通道的音符
	var channel_notes: Dictionary = {}  ## channel -> [NoteData]
	for rn in notes:
		if rn.channel == 9 and _piano_roll._muted_channels.has(rn.channel):
			continue
		if not channel_notes.has(rn.channel):
			channel_notes[rn.channel] = []
		var ticks_per_second := float(midi_res.tempo) / 60.0 * float(midi_res.timebase)
		var start_ticks := int(rn.start_time * ticks_per_second)
		var duration_ticks := int(rn.duration * ticks_per_second)
		channel_notes[rn.channel].append(NoteData.new(rn.pitch, start_ticks, duration_ticks, rn.velocity))
	# 构建 TrackData
	for ch in channel_notes:
		var track := TrackData.new()
		track.channel = ch
		track.notes = channel_notes[ch]
		if midi_res.tracks.size() > 0:
			# 从原始 track 获取乐器信息
			for orig_track in midi_res.tracks:
				if orig_track.channel == ch:
					track.instrument = orig_track.instrument
					track.name = orig_track.name
					break
		midi_data.tracks.append(track)
	# 保留原始 tempo_events / cc_events / pitch_bend_events / program_events
	midi_data.tempo_events = midi_res.tempo_events.duplicate(true)
	midi_data.cc_events = midi_res.cc_events.duplicate(true)
	midi_data.pitch_bend_events = midi_res.pitch_bend_events.duplicate(true)
	midi_data.program_events = midi_res.program_events.duplicate(true)
	# 写入文件
	var bytes := MidiWriter.encode(midi_data)
	var dir := "user://"
	# 尝试写到 addons/clef/output/（项目目录下）
	var output_dir := "res://addons/clef/output/"
	if DirAccess.dir_exists_absolute(output_dir):
		dir = output_dir
	var timestamp := Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "_")
	var path := dir + "edited_" + timestamp + ".mid"
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file:
		file.store_buffer(bytes)
		file.close()
		print("MIDI exported: ", path)
	else:
		push_error("Failed to export MIDI: ", path)
```

**Step 4: 检查 MidiResource 是否有 tempo_events 等字段**

```bash
grep -n "tempo_events\|cc_events\|pitch_bend_events\|program_events" addons/clef/midi_resource.gd
```

如果不存在，需要从原始 MidiData 复制到 MidiResource，或者直接从 MidiResource 的 tracks 反推。**备选方案**：如果 MidiResource 没有这些字段，导出时只保留音符数据（tempo_events 等设为空数组），功能仍然可用，只是丢失 CC/弯音数据。

**Step 5: 手动验证**

- 加载 MIDI → 修改几个音符（移动/删除）
- 右键 → "导出修改后的 MIDI"
- 检查 `addons/clef/output/` 下是否生成 `.mid` 文件
- 双击打开导出的 MIDI，验证修改生效

**Step 6: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd addons/clef/editor/clef_station.gd
git commit -m "feat(piano-roll): add MIDI export pipeline for edited notes"
```

---

## Phase 4: 标注与审查系统

**验收标准：** 可以右键音符添加标注（severity + 文字），标注在卷帘上显示为彩色三角标记，可导出为 Agent 反馈 JSON。

**前置：** Phase 3 的右键菜单和导出管线就绪。

### Task 4.1: Annotation 类 + 标注存储

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: 在 EditCommand 类之后添加 Annotation 类**

```gdscript
## 审查标注
class Annotation:
	var note_index: int       ## 指向 _notes 中的索引
	var text: String          ## 标注文字
	var severity: String      ## "info" | "warning" | "error"

	func _init(p_idx: int = 0, p_text: String = "", p_sev: String = "info") -> void:
		note_index = p_idx
		text = p_text
		severity = p_sev
```

**Step 2: 添加标注状态字段**

```gdscript
var _annotations: Array[Annotation] = []
var _annotation_popup: PanelContainer = null
```

**Step 3: 添加信号**

```gdscript
## 添加标注
signal annotation_added(note_index: int, text: String, severity: String)
```

**Step 4: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add Annotation class and storage"
```

### Task 4.2: 标注输入弹窗

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: 创建标注输入弹窗**

```gdscript
func _create_annotation_popup() -> void:
	_annotation_popup = PanelContainer.new()
	var vbox := VBoxContainer.new()
	# Severity 选择
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
	# 文字输入
	var text_label := Label.new()
	text_label.text = "备注:"
	vbox.add_child(text_label)
	var text_input := TextEdit.new()
	text_input.custom_minimum_size = Vector2(280, 60)
	vbox.add_child(text_input)
	# 按钮
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

	# 信号
	cancel_btn.pressed.connect(func():
		_annotation_popup.visible = false
	)
	confirm_btn.pressed.connect(func():
		_add_annotation_from_popup(sev_option.selected, text_input.text.strip_edges())
		_annotation_popup.visible = false
	)
```

**Step 2: 在 `_create_context_menu` 中添加 "添加标注" 菜单项**

在"编辑力度..."之后添加：

```gdscript
_context_menu.add_item("添加标注...", 4)
```

在 `_on_context_menu_item` 中添加 case：

```gdscript
4:  # 添加标注
	_open_annotation_popup()
```

**Step 3: 实现弹窗打开和标注添加**

```gdscript
func _open_annotation_popup() -> void:
	if _selection.is_empty():
		return
	if _annotation_popup == null:
		_create_annotation_popup()
	_annotation_popup.position = get_global_mouse_position() + Vector2(5, 5)
	_annotation_popup.visible = true


func _add_annotation_from_popup(sev_index: int, text: String) -> void:
	if text.is_empty():
		return
	var severity := ["info", "warning", "error"][sev_index] if sev_index < 3 else "info"
	for idx in _selection:
		var ann := Annotation.new(idx, text, severity)
		_annotations.append(ann)
		annotation_added.emit(idx, text, severity)
	# 记录到 undo（标注删除）
	var cmd := begin_command("annotation", "添加标注: %s" % text)
	cmd.before = {}
	cmd.after = {"annotation_count": _annotations.size()}
	commit_command(cmd)
	queue_redraw()
```

**Step 4: 手动验证**

- 右键音符 → "添加标注..." → 弹窗出现
- 选择 severity "error"，输入文字
- 确认后弹窗关闭

**Step 5: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add annotation input popup"
```

### Task 4.3: 标注渲染

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: 在 `_draw` 中添加标注绘制**

在 `_draw_playback_cursor()` 调用之后添加：

```gdscript
# 标注标记
_draw_annotations()
```

**Step 2: 实现 `_draw_annotations`**

```gdscript
func _draw_annotations() -> void:
	# 按严重度颜色
	var colors := {
		"info": Color(0.3, 0.7, 1.0),     # 蓝
		"warning": Color(1.0, 0.8, 0.2),   # 黄
		"error": Color(1.0, 0.3, 0.3),     # 红
	}
	# 收集每个音符上的标注数，用于水平错开
	var note_ann_count: Dictionary = {}
	for ann in _annotations:
		if ann.note_index >= _notes.size():
			continue
		var idx := ann.note_index
		if not note_ann_count.has(idx):
			note_ann_count[idx] = 0

	var drawn_count: Dictionary = {}
	for ann in _annotations:
		if ann.note_index >= _notes.size():
			continue
		var note := _notes[ann.note_index]
		var x := _time_to_x(note.start_time)
		var y := _pitch_to_y(note.pitch + 1)
		var idx := ann.note_index
		var offset := drawn_count.get(idx, 0)
		drawn_count[idx] = offset + 1
		var color: Color = colors.get(ann.severity, colors["info"])
		# 小三角标记
		var tri_x := x + offset * 8.0
		var tri_size := 6.0
		var points := PackedVector2Array([
			Vector2(tri_x, y - 2),
			Vector2(tri_x + tri_size, y - 2),
			Vector2(tri_x + tri_size / 2, y - tri_size - 2),
		])
		draw_colored_polygon(points, color)
```

**Step 3: 手动验证**

添加标注后，音符上方出现彩色小三角，不同 severity 不同颜色。

**Step 4: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): render annotation markers on notes"
```

### Task 4.4: Agent 反馈 JSON 导出

**Files:**
- Modify: `addons/clef/editor/clef_station.gd`

**Step 1: 在右键菜单中添加 "生成 Agent 反馈" 选项**

在 `_create_context_menu` 中添加：

```gdscript
_context_menu.add_item("生成 Agent 反馈", 11)
```

在 `_on_context_menu_item` 中添加：

```gdscript
11:  # Agent 反馈
	agent_feedback_requested.emit(_get_agent_feedback())
```

**Step 2: 添加信号和导出方法**

在 `piano_roll.gd` 中：

```gdscript
signal agent_feedback_requested(feedback: Dictionary)

func _get_agent_feedback() -> Dictionary:
	var annotations_data := []
	for ann in _annotations:
		if ann.note_index >= _notes.size():
			continue
		var note := _notes[ann.note_index]
		annotations_data.append({
			"channel": note.channel,
			"pitch": note.pitch,
			"severity": ann.severity,
			"note": ann.text,
		})
	# TODO: 收集 modifications（需要额外的编辑追踪，Phase 2 的 command 已记录）
	return {
		"version": 1,
		"annotations": annotations_data,
	}
```

**Step 3: 在 `clef_station.gd` 中连接信号并保存 JSON**

```gdscript
_piano_roll.agent_feedback_requested.connect(func(feedback: Dictionary):
	var output_dir := "res://addons/clef/output/"
	var timestamp := Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "_")
	var path := output_dir + "agent_feedback_" + timestamp + ".json"
	var json_str := JSON.stringify(feedback, "\t")
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file:
		file.store_string(json_str)
		file.close()
		print("Agent feedback exported: ", path)
)
```

**Step 4: 手动验证**

添加标注 → 右键 → "生成 Agent 反馈" → 检查 JSON 文件。

**Step 5: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd addons/clef/editor/clef_station.gd
git commit -m "feat(piano-roll): add Agent feedback JSON export"
```

---

## Phase 5: 临时音符与屏蔽

**验收标准：** 可以添加临时试听音符（虚线边框），可以屏蔽原始音符（半透明 + 删除线），导出时合并处理。

**前置：** Phase 3 的导出管线就绪。

### Task 5.1: 屏蔽系统

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: 添加屏蔽状态字段**

```gdscript
var _muted_indices: Array[int] = []  ## 屏蔽的原始音符索引
```

**Step 2: 在右键菜单中添加 "屏蔽/恢复" 选项**

```gdscript
_context_menu.add_item("屏蔽（临时静音）", 5)
```

```gdscript
5:  # 屏蔽
	_toggle_mute_selected()
```

**Step 3: 实现屏蔽方法**

```gdscript
func _toggle_mute_selected() -> void:
	if _selection.is_empty():
		return
	var to_toggle := _selection.duplicate()
	var newly_muted := []
	var newly_unmuted := []
	for idx in to_toggle:
		var found := _muted_indices.find(idx)
		if found >= 0:
			_muted_indices.remove_at(found)
			newly_unmuted.append(idx)
		else:
			_muted_indices.append(idx)
			newly_muted.append(idx)
	if not newly_muted.is_empty() or not newly_unmuted.is_empty():
		var cmd := begin_command("mute", "屏蔽 %d / 恢复 %d 个音符" % [newly_muted.size(), newly_unmuted.size()])
		cmd.before = {"muted_indices": newly_unmuted.duplicate()}
		cmd.after = {"muted_indices": newly_muted.duplicate()}
		commit_command(cmd)
	queue_redraw()
```

**Step 4: 修改 `_draw_notes` 渲染屏蔽态**

```gdscript
# 在音符绘制循环中添加
if _muted_indices.has(i):
	# 半透明 + 删除线
	color.a = 0.3
	draw_rect(Rect2(x, y, w, h), color)
	draw_line(Vector2(x, y + h / 2), Vector2(x + w, y + h / 2), Color(1, 0.3, 0.3), 1.5)
	continue
```

**Step 5: 手动验证**

选中音符 → 右键 "屏蔽" → 半透明 + 红色删除线 → 再次右键 "恢复"

**Step 6: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add note muting system"
```

### Task 5.2: 临时音符添加

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: 添加临时音符字段和编辑模式**

```gdscript
var _temp_notes: Array[RollNote] = []  ## 临时试听音符
enum EditMode { SELECT, ANNOTATE, ADD_NOTE }
var _edit_mode: EditMode = EditMode.SELECT
```

**Step 2: 在左键点击空白时处理 ADD_NOTE 模式**

在 `_gui_input` 的左键点击空白分支中：

```gdscript
if hit["index"] < 0 and _edit_mode == EditMode.ADD_NOTE:
	# 添加临时音符
	var pitch := _y_to_pitch(mb.position.y)
	var time := _pixel_to_time(mb.position.x)
	var channel := 0  # 默认通道
	if not _selection.is_empty():
		channel = _notes[_selection[0]].channel
	var new_note := RollNote.new(channel, pitch, time, 0.5, 100)
	_temp_notes.append(new_note)
	queue_redraw()
	note_edited.emit()
	# 继续执行 seek（如果不在音符上）
```

**Step 3: 渲染临时音符（虚线边框）**

在 `_draw_notes` 末尾添加：

```gdscript
# 临时音符
for tn in _temp_notes:
	var x := _time_to_x(tn.start_time)
	var w := tn.duration * _pixels_per_second
	var y := _pitch_to_y(tn.pitch + 1)
	var h := _pixels_per_note - 1.0
	# 虚线边框
	draw_rect(Rect2(x, y, w, h), Color(0.3, 1.0, 0.3, 0.4))
	draw_rect(Rect2(x, y, w, h), Color(0.3, 1.0, 0.3, 0.8), false, 1.0)
```

**Step 4: 右键临时音符可删除**

在右键菜单处理中，如果命中了临时音符（通过额外检测），显示"删除临时音符"选项。为简化，临时音符通过单独的菜单项处理：

```gdscript
_context_menu.add_item("清除所有临时音符", 12)
```

```gdscript
12:  # 清除临时音符
	_temp_notes.clear()
	queue_redraw()
```

**Step 5: 导出合并策略**

修改 `clef_station.gd` 中的导出方法，在构建 channel_notes 时同时包含临时音符：

```gdscript
# 在 _on_piano_roll_export_requested 中，遍历 notes 时同时遍历 _temp_notes
for rn in notes:
	# ... 原有逻辑 ...
for tn in _piano_roll._temp_notes:
	if tn.channel == 9 and _piano_roll._muted_channels.has(tn.channel):
		continue
	# ... 同样的 ticks 转换逻辑 ...
```

注意：屏蔽音符在导出时跳过。

**Step 6: 手动验证**

切换到 ADD_NOTE 模式 → 点击网格 → 绿色虚线音符出现 → 导出验证包含临时音符。

**Step 7: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd addons/clef/editor/clef_station.gd
git commit -m "feat(piano-roll): add temporary notes and mute system"
```

---

## Phase 6: ABC 导出

**验收标准：** 从修改后的 MIDI 文件反向转换为 ABC 格式，保存到 `addons/clef/output/`。

**前置：** Phase 3/5 的 MIDI 导出管线就绪（导出的 MIDI 作为 ABC 转换的输入）。

### Task 6.1: clef_tools.py 新增 midi-to-abc 子命令

**Files:**
- Modify: `.claude/skills/clef-compose/scripts/clef_tools.py`

**Step 1: 实现 `midi_to_abc` 函数**

在 `clef_tools.py` 中添加：

```python
def midi_to_abc(midi_path: str, output_path: str) -> None:
    """Convert MIDI file to ABC notation using music21."""
    from music21 import converter, midi
    mf = midi.MidiFile()
    mf.open(midi_path)
    mf.read()
    mf.close()
    score = midi.translate.midiFileToStream(mf)
    abc_str = converter.freezeStr(score, fmt='abc')
    Path(output_path).write_text(abc_str, encoding='utf-8')
    print(f"ABC exported: {output_path}")
```

**Step 2: 注册子命令**

在 `clef_tools.py` 的 CLI 参数解析中添加：

```python
subparsers.add_parser('midi-to-abc', help='Convert MIDI to ABC notation')
# 在子命令分发中：
elif args.command == 'midi-to-abc':
    midi_to_abc(args.input, args.output)
```

**Step 3: 编写测试**

文件：`.claude/skills/clef-compose/tests/test_midi_to_abc.py`

```python
def test_midi_to_abc(tmp_path):
    """Test MIDI to ABC conversion produces valid output."""
    from scripts.clef_tools import midi_to_abc
    midi_path = "tests/fixtures/sample.mid"  # 或使用已知的测试 MIDI
    abc_path = str(tmp_path / "output.abc")
    # 需要一个真实的 MIDI 文件来测试
    # 这里先验证函数存在且参数正确
    midi_to_abc(midi_path, abc_path)
    content = Path(abc_path).read_text(encoding='utf-8')
    assert 'X:' in content  # ABC 文件头部
    assert 'K:' in content  # 调号标记
```

**Step 4: 运行测试**

```bash
cd .claude/skills/clef-compose && python -m pytest tests/test_midi_to_abc.py -v
```

**Step 5: Commit**

```bash
git add .claude/skills/clef-compose/scripts/clef_tools.py .claude/skills/clef-compose/tests/test_midi_to_abc.py
git commit -m "feat(clef-tools): add midi-to-abc conversion subcommand"
```

### Task 6.2: Piano Roll ABC 导出触发

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`（右键菜单添加 ABC 导出选项）
- Modify: `addons/clef/editor/clef_station.gd`（连接信号，调用 Python 脚本）

**Step 1: 在右键菜单中添加 "导出 ABC" 选项**

```gdscript
_context_menu.add_item("导出修改后的 ABC", 13)
```

```gdscript
13:  # 导出 ABC
	abc_export_requested.emit()
```

**Step 2: 添加信号**

```gdscript
signal abc_export_requested()
```

**Step 3: 在 clef_station.gd 中处理 ABC 导出**

```gdscript
_piano_roll.abc_export_requested.connect(func():
	# 先导出 MIDI，再调用 Python 转换
	# 或直接用 Godot 内置方法（如果不需要 music21）
	# 简易方案：调用 OS.execute 运行 Python 脚本
	var midi_path := "res://addons/clef/output/_tmp_edited.mid"
	var abc_path := "res://addons/clef/output/edited_" + Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "_") + ".abc"
	# 先触发 MIDI 导出（复用现有逻辑）
	_on_piano_roll_export_requested(_piano_roll.get_notes())
	# 然后调用 Python
	var script_path := ProjectSettings.globalize_path("res://.claude/skills/clef-compose/scripts/clef_tools.py")
	var abs_midi := ProjectSettings.globalize_path(midi_path)
	var abs_abc := ProjectSettings.globalize_path(abc_path)
	OS.execute("python", [script_path, "midi-to-abc", abs_midi, "-o", abs_abc])
	print("ABC export triggered: ", abc_path)
)
```

**Step 4: 手动验证**

- 修改 MIDI → 右键 "导出 ABC" → 检查 `.abc` 文件生成
- 打开 ABC 文件验证内容合理

**Step 5: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd addons/clef/editor/clef_station.gd
git commit -m "feat(piano-roll): add ABC export via Python midi-to-abc pipeline"
```

---

## 验收总表

| Phase | 验收标准 | 依赖 |
|-------|---------|------|
| **1** | 选中高亮、Ctrl+Z/Ctrl+Shift+Z 撤销重做 | 无（基于现有 PianoRoll） |
| **2** | 拖拽移动/调整时长、Delete 删除、所有操作可撤销 | Phase 1 |
| **3** | 右键菜单（删除/音高/力度/导出）、MIDI 文件导出到 output/ | Phase 2 |
| **4** | 添加标注、彩色三角渲染、Agent 反馈 JSON 导出 | Phase 3 |
| **5** | 屏蔽音符（半透明+删除线）、临时音符（虚线边框）、导出合并 | Phase 3 |
| **6** | MIDI→ABC 转换、右键菜单 ABC 导出 | Phase 3/5 |
