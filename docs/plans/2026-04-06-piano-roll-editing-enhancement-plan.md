# Piano Roll 编辑功能增强实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Piano Roll 添加轨道管理、音符创建、复制粘贴功能

**Architecture:** 在现有 `piano_roll.gd`（~1100行）上增量改造。轨道选择器改造现有 legend bar 绘制+交互；音符创建移除半成品 ADD_NOTE 改为拖动创建；复制粘贴复用现有 `_unhandled_key_input` 快捷键模式。新建 `gm_instrument_selector.gd` 作为独立弹窗组件。

**Tech Stack:** GDScript, Godot 4.6 Control/Tree/AcceptDialog

**Design doc:** `docs/plans/2026-04-06-piano-roll-editing-enhancement-design.md`

---

### Task 1: RollNote.duplicate() + 剪贴板状态

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:40-52` (RollNote class)
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:128-185` (状态变量区)

**Step 1: 给 RollNote 添加 duplicate() 方法**

在 `piano_roll.gd` 的 `RollNote` 类内（line 52 之后），`_init` 函数下方添加：

```gdscript
func duplicate() -> RollNote:
	return RollNote.new(channel, pitch, start_time, duration, velocity)
```

**Step 2: 添加剪贴板状态变量**

在 `piano_roll.gd` line 179（`_temp_notes` 附近）添加：

```gdscript
## 剪贴板
var _clipboard: Array[RollNote] = []
var _clipboard_ref_time: float = 0.0

## 当前选中轨道
var _active_channel: int = 0
```

**Step 3: 在 Godot 编辑器中验证脚本无语法错误**

Run: 打开 Godot 编辑器，确认 `piano_roll.gd` 无报错

**Step 4: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add RollNote.duplicate() and clipboard state variables"
```

---

### Task 2: 撤销系统扩展 — 支持批量添加

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:1022-1061` (`_apply_snapshot`)

当前的 `_apply_snapshot` 只支持单个 `added_index`（line 1053-1054），粘贴操作需要一次添加多个音符。

**Step 1: 在 `_apply_snapshot` 中添加 `added_indices` 处理**

在 line 1053 的 `elif snapshot.has("added_index"):` 之前，插入：

```gdscript
elif snapshot.has("added_indices"):
	var indices: Array = snapshot["added_indices"]
	var sorted_indices := indices.duplicate()
	sorted_indices.sort_custom(func(a, b): return a > b)
	for idx in sorted_indices:
		if idx >= 0 and idx < _notes.size():
			_notes.remove_at(idx)
```

**Step 2: 验证**

打开 Godot 编辑器，确认无语法错误

**Step 3: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): extend undo system for batch add (added_indices)"
```

---

### Task 3: 复制（Ctrl+C）

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:451-505` (`_unhandled_key_input`)

**Step 1: 在 `_unhandled_key_input` 中添加 Ctrl+C 处理**

在现有的 Ctrl+Y 处理之后（约 line 467），添加：

```gdscript
# Ctrl+C — 复制选中音符
if key.ctrl_pressed and not key.shift_pressed and key.keycode == KEY_C:
	if not _selection.is_empty():
		get_viewport().set_input_as_handled()
		var sorted_sel := _selection.duplicate()
		sorted_sel.sort()
		_clipboard.clear()
		_clipboard_ref_time = INF
		for idx in sorted_sel:
			if idx >= 0 and idx < _notes.size():
				var n: RollNote = _notes[idx]
				_clipboard.append(n.duplicate())
				if n.start_time < _clipboard_ref_time:
					_clipboard_ref_time = n.start_time
		if _clipboard_ref_time == INF:
			_clipboard_ref_time = 0.0
	return
```

**Step 2: 验证**

打开 Godot 编辑器，进入 EDITING 模式，选中几个音符，按 Ctrl+C，无报错

**Step 3: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add Ctrl+C copy selected notes"
```

---

### Task 4: 粘贴（Ctrl+V）

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:451-505` (`_unhandled_key_input`)

**Step 1: 在 `_unhandled_key_input` 的 Ctrl+C 之后添加 Ctrl+V 处理**

```gdscript
# Ctrl+V — 粘贴音符
if key.ctrl_pressed and not key.shift_pressed and key.keycode == KEY_V:
	if _clipboard.is_empty():
		return
	get_viewport().set_input_as_handled()
	var target_time: float
	var mouse_pos := get_local_mouse_position()
	if Rect2(Vector2.ZERO, size).has_point(mouse_pos):
		target_time = _pixel_to_time(mouse_pos.x)
	elif _playback_position >= 0.0:
		target_time = _playback_position
	else:
		target_time = _view_offset
	var time_offset := target_time - _clipboard_ref_time
	var cmd := begin_command("add", "粘贴 %d 个音符" % _clipboard.size())
	var added_indices: Array[int] = []
	_selection.clear()
	for cn in _clipboard:
		var new_note := RollNote.new(
			_active_channel,
			cn.pitch,
			maxf(0.0, cn.start_time + time_offset),
			cn.duration,
			cn.velocity
		)
		_notes.append(new_note)
		added_indices.append(_notes.size() - 1)
		_selection.append(_notes.size() - 1)
	cmd.before = {"added_indices": added_indices.duplicate()}
	cmd.after = {}
	commit_command(cmd)
	queue_redraw()
	return
```

**Step 2: 验证**

1. 复制几个音符 → Ctrl+V → 验证新音符出现在正确位置、归属当前 channel
2. Ctrl+Z → 验证撤销删除所有粘贴的音符
3. 多次 Ctrl+V → 验证以相同偏移叠放

**Step 3: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add Ctrl+V paste notes at mouse/playhead position"
```

---

### Task 5: 音符创建 — 移除 ADD_NOTE，添加拖动创建状态

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:184-185` (EditSubMode enum)
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:179` (_temp_notes)
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:608-629` (_handle_left_press no-hit 分支)
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:632-680` (_handle_left_release)
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd` (_draw_notes, _draw_temp_notes)

**Step 1: 添加音符创建状态变量**

在 `piano_roll.gd` 状态变量区（`_temp_notes` 附近 line 179），替换 `_temp_notes` 为：

```gdscript
## 拖动创建音符状态
var _creating_note: bool = false
var _create_pitch: int = 60
var _create_start_time: float = 0.0
var _preview_note: RollNote = null  # 创建预览
```

> 注意：保留 `_temp_notes` 声明但清空引用，避免其他地方访问报错。改为 `var _temp_notes: Array[RollNote] = []  ## 废弃，保留兼容`

**Step 2: 移除 EditSubMode.ADD_NOTE**

将 line 184：
```gdscript
enum EditSubMode { SELECT, ADD_NOTE }
```
改为：
```gdscript
enum EditSubMode { SELECT }
```

**Step 3: 改造 `_handle_left_press` 空白区域分支**

将 line 609-629 的 else 分支替换为：

```gdscript
else:
	if _mode == Mode.EDITING:
		# 拖动创建音符
		_creating_note = true
		_create_pitch = clampi(_y_to_pitch(mb.position.y), 0, 127)
		_create_start_time = maxf(0.0, _pixel_to_time(mb.position.x))
		if snap_enabled:
			_create_start_time = round(_create_start_time / snap_interval) * snap_interval
		_preview_note = null
	else:
		_selection.clear()
		_box_selecting = true
		_box_select_start = mb.position
		_box_select_end = mb.position
	queue_redraw()
```

**Step 4: 在 `_gui_input` 的 mouse motion 处理中添加创建预览**

找到 `_gui_input` 中处理 `InputEventMouseMotion` 的位置（搜索 `MOUSE_BUTTON_LEFT` 和 motion），在现有拖拽逻辑之后添加：

```gdscript
if _creating_note and mb.button_mask & MOUSE_BUTTON_MASK_LEFT:
	var current_time := _pixel_to_time(mb.position.x)
	if snap_enabled:
		current_time = round(current_time / snap_interval) * snap_interval
	var start_t := minf(_create_start_time, current_time)
	var dur := absf(current_time - _create_start_time)
	_preview_note = RollNote.new(_active_channel, _create_pitch, start_t, dur, 100)
	queue_redraw()
```

**Step 5: 改造 `_handle_left_release` 添加创建确认**

在 `_handle_left_release` 函数开头（line 632 之后），拖拽处理之前添加：

```gdscript
# 拖动创建音符确认
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
	else:
		# 单击 → 默认 1 拍音符
		var beat_dur := 60.0 / 120.0  # 默认 120 BPM 下一拍
		if _duration > 0.0:
			# 尝试从 MIDI 数据推断，否则用默认值
			pass
		var new_note := RollNote.new(_active_channel, _create_pitch, _create_start_time, beat_dur, 100)
		_notes.append(new_note)
		var idx := _notes.size() - 1
		var cmd := begin_command("add", "创建音符")
		cmd.before = {"added_index": idx}
		cmd.after = {}
		commit_command(cmd)
		_selection.clear()
		_selection.append(idx)
	_preview_note = null
	queue_redraw()
	return
```

**Step 6: 在 `_draw_notes` 中添加预览绘制**

找到 `_draw_notes` 函数末尾，添加：

```gdscript
# 绘制创建预览音符
if _preview_note != null:
	var pn := _preview_note
	var x1 := _time_to_x(pn.start_time)
	var x2 := _time_to_x(pn.start_time + pn.duration)
	var y1 := _pitch_to_y(pn.pitch + 1)
	var y2 := _pitch_to_y(pn.pitch)
	var rect := Rect2(minf(x1, x2), minf(y1, y2), absf(x2 - x1), absf(y2 - y1))
	draw_rect(rect, Color(0.2, 0.8, 0.3, 0.5))
	draw_rect(rect, Color(0.3, 1.0, 0.4, 0.8), false, 1.0)
```

**Step 7: 清理 _draw_temp_notes 调用**

搜索 `_temp_notes` 的所有引用（绘制、set_notes、clear_notes 等），移除或替换为空操作。`_temp_notes` 保留声明但不再使用。

**Step 8: 验证**

1. 进入 EDITING 模式，在空白处点击拖动 → 预览音符出现 → 松手后音符被创建
2. 在空白处单击 → 创建默认 1 拍音符
3. Ctrl+Z → 撤销创建
4. 创建的音符 channel = _active_channel

**Step 9: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): replace ADD_NOTE with drag-to-create notes"
```

---

### Task 6: Legend Bar 轨道选择器交互

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:805-837` (`_draw_legend`)
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd:507-515` (`_gui_input` 入口)

**Step 1: 改造 `_draw_legend` 绘制选中状态和 "+" 按钮**

替换 `_draw_legend` 函数（line 805-837）为：

```gdscript
func _draw_legend() -> void:
	# 背景
	draw_rect(Rect2(0, 0, size.x, _LEGEND_HEIGHT), _LEGEND_BG)
	# 分隔线
	draw_line(Vector2(0, _LEGEND_HEIGHT), Vector2(size.x, _LEGEND_HEIGHT), Color(0.2, 0.2, 0.25))

	var x := 8.0
	var font := ThemeDB.fallback_font
	var font_size := 12
	var plus_width := 28.0  # "+" 按钮宽度

	for ch in _active_channels:
		if _muted_channels.has(ch):
			continue
		var preset: int = _channel_instruments.get(ch, 0)
		var name: String = "Ch%d" % ch if ch == 9 else "Ch%d %s" % [ch, _GM_NAMES[preset] if preset < _GM_NAMES.size() else "?"]
		var color := ChannelColors.COLORS[ch % 16]

		# 选中高亮背景
		if ch == _active_channel:
			draw_rect(Rect2(x - 2, 2, font.get_string_size(name, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x + 28, _LEGEND_HEIGHT - 4),
				Color(0.15, 0.15, 0.2))
			# 选中边框
			draw_rect(Rect2(x - 2, 2, font.get_string_size(name, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x + 28, _LEGEND_HEIGHT - 4),
				Color(1.0, 1.0, 1.0, 0.6), false, 1.0)

		# 色块
		draw_rect(Rect2(x, 5, 18, 18), color)
		if ch == _active_channel:
			draw_rect(Rect2(x, 5, 18, 18), Color(1.0, 1.0, 1.0, 0.8), false, 1.5)

		# 文字
		draw_string(font, Vector2(x + 24, _LEGEND_HEIGHT / 2 + font_size / 2 - 1),
			name, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color(0.7, 0.7, 0.75) if ch != _active_channel else Color(1.0, 1.0, 1.0))

		x += font.get_string_size(name, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x + 32
		if x > size.x - plus_width - 16:
			break

	# "+" 按钮
	var plus_rect := Rect2(size.x - plus_width, 0, plus_width, _LEGEND_HEIGHT)
	draw_rect(plus_rect, Color(0.12, 0.12, 0.16))
	draw_line(Vector2(plus_rect.position.x + plus_rect.size.x, 0),
		Vector2(plus_rect.position.x + plus_rect.size.x, _LEGEND_HEIGHT), Color(0.2, 0.2, 0.25))
	# "+" 文字
	var plus_text := "+"
	var ps := font.get_string_size(plus_text, HORIZONTAL_ALIGNMENT_CENTER, -1, 16)
	draw_string(font, Vector2(plus_rect.position.x + plus_rect.size.x / 2 - ps.x / 2, _LEGEND_HEIGHT / 2 + 4),
		plus_text, HORIZONTAL_ALIGNMENT_CENTER, -1, 16, Color(0.6, 0.8, 0.6))
```

**Step 2: 在 `_gui_input` 入口处添加 legend 区域拦截**

在 `_gui_input` 函数开头（line 507 之后），现有模式检查之前添加：

```gdscript
func _gui_input(event: InputEvent) -> void:
	# Legend bar 交互
	if event is InputEventMouseButton and event.position.y < _LEGEND_HEIGHT:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			# 检查是否点击 "+"
			var plus_x := size.x - 28.0
			if mb.position.x >= plus_x:
				_open_gm_selector_popup()
				accept_event()
				return
			# 检查是否点击轨道标签
			_handle_legend_click(mb.position.x)
			accept_event()
			return
	# ... 后续现有逻辑不变
```

**Step 3: 添加 `_handle_legend_click` 辅助函数**

```gdscript
func _handle_legend_click(click_x: float) -> void:
	var font := ThemeDB.fallback_font
	var font_size := 12
	var x := 8.0
	for ch in _active_channels:
		if _muted_channels.has(ch):
			continue
		var preset: int = _channel_instruments.get(ch, 0)
		var name: String = "Ch%d" % ch if ch == 9 else "Ch%d %s" % [ch, _GM_NAMES[preset] if preset < _GM_NAMES.size() else "?"]
		var label_width := font.get_string_size(name, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x + 32
		if click_x >= x and click_x < x + label_width:
			if _active_channel != ch:
				_active_channel = ch
				queue_redraw()
			return
		x += label_width
		if x > size.x - 36:
			break
```

**Step 4: 添加 `_open_gm_selector_popup` 桩函数**

```gdscript
func _open_gm_selector_popup() -> void:
	# Task 7 实现
	pass
```

**Step 5: 验证**

1. 打开编辑器，加载 MIDI，legend bar 显示轨道标签
2. 点击不同标签 → _active_channel 切换，选中高亮变化
3. 点击 "+" 区域 → 无报错（桩函数）

**Step 6: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): interactive legend bar with track selector and add button"
```

---

### Task 7: GM 音色选择弹窗

**Files:**
- Create: `addons/clef/editor/piano_roll/gm_instrument_selector.gd`

**Step 1: 创建 GM 音色选择弹窗脚本**

```gdscript
## GM 音色选择弹窗
## 按 GM 标准类别分组，选择后通过 instrument_selected 信号返回 channel + preset
extends AcceptDialog

signal instrument_selected(preset: int)

# GM 类别定义（16 类，每类 8 个音色）
const CATEGORIES: Array[Dictionary] = [
	{"name": "Piano", "start": 0},
	{"name": "Chromatic Percussion", "start": 8},
	{"name": "Organ", "start": 16},
	{"name": "Guitar", "start": 24},
	{"name": "Bass", "start": 32},
	{"name": "Strings", "start": 40},
	{"name": "Ensemble", "start": 48},
	{"name": "Brass", "start": 56},
	{"name": "Reed", "start": 64},
	{"name": "Pipe", "start": 72},
	{"name": "Synth Lead", "start": 80},
	{"name": "Synth Pad", "start": 88},
	{"name": "Synth Effects", "start": 96},
	{"name": "Ethnic", "start": 104},
	{"name": "Percussive", "start": 112},
	{"name": "Sound Effects", "start": 120},
]

const GM_NAMES: PackedStringArray = [
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

var _tree: Tree

func _ready() -> void:
	title = "选择音色"
	min_size = Vector2(320, 420)
	size = Vector2(320, 420)
	# 移除默认 OK 按钮
	get_ok_button().text = "取消"

	var vbox := VBoxContainer.new()
	vbox.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT, Control.PRESET_MODE_KEEP_SIZE, 8)
	add_child(vbox)

	_tree = Tree.new()
	_tree.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_tree.hide_root = true
	_tree.columns = 1
	vbox.add_child(_tree)

	# 构建树
	var root := _tree.create_item()
	for cat in CATEGORIES:
		var cat_item := _tree.create_item(root)
		cat_item.set_text(0, cat["name"])
		cat_item.set_collapsed(true)
		for i in range(8):
			var preset := cat["start"] + i
			if preset >= GM_NAMES.size():
				break
			var item := _tree.create_item(cat_item)
			item.set_text(0, "%d: %s" % [preset, GM_NAMES[preset]])
			item.set_metadata(0, preset)

	_tree.item_activated.connect(_on_item_activated)
	_tree.item_selected.connect(_on_item_selected)

	# 双击选择
	_tree.set_allow_reselect(true)


func _on_item_selected() -> void:
	var item := _tree.get_selected()
	if item and item.get_metadata(0) != null:
		var preset: int = item.get_metadata(0)
		instrument_selected.emit(preset)
		hide()


func _on_item_activated() -> void:
	_on_item_selected()
```

**Step 2: 验证**

在 Godot 编辑器中加载脚本，确认无语法错误

**Step 3: Commit**

```bash
git add addons/clef/editor/piano_roll/gm_instrument_selector.gd
git commit -m "feat(piano-roll): add GM instrument selector popup dialog"
```

---

### Task 8: 新增轨道 — 集成弹窗 + ClefStation 同步

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd` (`_open_gm_selector_popup`)
- Modify: `addons/clef/editor/clef_station.gd` (channel 同步 + 导出)

**Step 1: 实现 `_open_gm_selector_popup`**

替换 `piano_roll.gd` 中的桩函数：

```gdscript
var _gm_selector: Control = null

func _open_gm_selector_popup() -> void:
	if _gm_selector == null:
		_gm_selector = preload("res://addons/clef/editor/piano_roll/gm_instrument_selector.gd").new()
		_gm_selector.instrument_selected.connect(_on_instrument_selected)
		add_child(_gm_selector)
	_gm_selector.position = get_global_mouse_position() + Vector2(10, 10)
	_gm_selector.popup_centered()


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

	# 通知外部
	track_changed.emit(_active_channel, preset)
	queue_redraw()
```

**Step 2: 添加 track_changed 信号**

在 `piano_roll.gd` 信号区（line 16-20 附近）添加：

```gdscript
## 轨道变更（新增轨道时通知 ClefStation 同步）
signal track_changed(channel: int, preset: int)
```

**Step 3: ClefStation 连接信号并同步**

在 `clef_station.gd` 中找到 PianoRoll 初始化的位置（搜索 `piano_roll.note_edited`），添加信号连接：

```gdscript
_piano_roll.track_changed.connect(_on_track_changed)
```

添加处理函数：

```gdscript
func _on_track_changed(channel: int, preset: int) -> void:
	# 同步到 mini mixer
	_mini_mixer.set_channel_instrument(channel, preset)
	# 更新导出用的 channel_instruments
	if not channel in _channel_instruments:
		_channel_instruments[channel] = preset
```

**Step 4: 导出时包含新增轨道**

在 `clef_station.gd` 的导出逻辑中（搜索 `export_requested` 或 MIDI 导出），确保新增 channel 的 Program Change 事件被写入。检查现有的导出流程是否已遍历 `_channel_instruments`，如果是则无需额外修改。

**Step 5: 验证**

1. 点击 legend "+" → 弹出音色选择器
2. 选择一个音色 → 新轨道出现，_active_channel 切换
3. 在新轨道上创建音符 → channel 正确
4. 导出 MIDI → 新轨道数据包含在内

**Step 6: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git add addons/clef/editor/piano_roll/gm_instrument_selector.gd
git add addons/clef/editor/clef_station.gd
git commit -m "feat(piano-roll): add track creation via GM instrument selector"
```

---

### Task 9: 端到端验证与清理

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd` (清理废弃代码)

**Step 1: 清理废弃的 ADD_NOTE 相关代码**

搜索并清理：
- `EditSubMode.ADD_NOTE` 的所有引用（已移除 enum 值，确保无残留）
- `_temp_notes` 的所有绘制和逻辑代码（保留声明标记为废弃）
- `piano_roll_actions.gd` 中对 ADD_NOTE 的引用（如有）

**Step 2: 端到端功能验证**

| 功能 | 验证步骤 | 预期结果 |
|------|---------|---------|
| 轨道选择 | 点击 legend 中不同标签 | _active_channel 切换，高亮变化 |
| 新增轨道 | 点击 "+", 选择 Violin | 新轨道出现，选中状态 |
| 创建音符 | EDITING 模式空白处拖动 | 预览→松手→音符创建，归属 active channel |
| 单击创建 | 空白处单击 | 创建 1 拍默认音符 |
| 撤销创建 | 创建后 Ctrl+Z | 音符被删除 |
| 复制 | 选中音符 Ctrl+C | 剪贴板有数据 |
| 粘贴 | Ctrl+V | 音符出现在鼠标位置 |
| 粘贴撤销 | Ctrl+Z | 所有粘贴音符被删除 |
| 跨轨道粘贴 | 切换轨道后 Ctrl+V | 粘贴音符归属新轨道 |

**Step 3: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git add addons/clef/editor/piano_roll/piano_roll_actions.gd
git commit -m "chore(piano-roll): cleanup deprecated ADD_NOTE code"
```
