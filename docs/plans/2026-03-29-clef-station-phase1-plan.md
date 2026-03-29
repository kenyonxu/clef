# Clef Station Phase 1 — 基础框架 Implementation Plan

> **Status:** COMPLETED (2026-03-29)
> **Commit:** `5a444c3` feat: add Clef Station editor main screen (Phase 1)

**Goal:** 为 Clef 插件创建 Godot 编辑器主屏幕「Clef Station」，建立三栏布局骨架，并扩展 MidiStreamPlayer 信号供后续面板使用。

**Architecture:** 通过 `EditorInterface.get_editor_main_screen().add_child()` 注册主屏幕，`_make_visible()` 控制显隐。主界面 `ClefStation` 使用 HSplitContainer 三栏布局，左/右栏可折叠。MidiStreamPlayer 新增 4 个信号（note_off/cc/pitch_bend/program_change），在 `_process_event` 和 `_preprocess_events_up_to` 中发射。

**Tech Stack:** GDScript, Godot 4.6 EditorPlugin API (`_has_main_screen` / `_make_visible`), AudioServer bus API

---

### Task 1: 扩展 MidiStreamPlayer 信号 — DONE

**Files:**
- Modify: `addons/clef/player/midi_stream_player.gd:18-20` (signal 声明区)
- Modify: `addons/clef/player/midi_stream_player.gd:426-466` (`_process_event` 函数)

**Step 1: 添加新信号声明**

在 `midi_stream_player.gd` 第 18-20 行现有信号之后，添加 4 个新信号：

```gdscript
signal note_triggered(channel: int, pitch: int, velocity: int)
signal note_released(channel: int, pitch: int)
signal cc_received(channel: int, controller: int, value: int)
signal pitch_bend_received(channel: int, value: int)
signal program_changed(channel: int, preset_index: int)
signal finished
signal progress_updated(position: float, duration: float)
```

**Step 2: 在 `_process_event` 中发射信号**

在 `_process_event` 函数中对应分支添加 `emit` 调用：

`note_off` 分支（约第 451 行），在 `_voice_pool.stop_note` 之后添加：
```gdscript
"note_off":
	var ch: int = event["channel"]
	if _channel_states[ch]._sustain:
		for voice in _voice_pool.get_active_voices_for_channel(ch):
			if voice.key == event["pitch"] and not voice.is_idle():
				voice._sustained = true
	else:
		_voice_pool.stop_note(ch, event["pitch"])
	note_released.emit(ch, event["pitch"])
```

`program_change` 分支（约第 459 行）：
```gdscript
"program_change":
	_channel_instruments[event["channel"]] = event["preset_index"]
	program_changed.emit(event["channel"], event["preset_index"])
```

`control_change` 分支（约第 463 行），在 `_process_cc(event)` 之前添加：
```gdscript
"control_change":
	cc_received.emit(event["channel"], event["controller"], event["value"])
	_process_cc(event)
```

`pitch_bend` 分支（约第 465 行），在 `_process_pitch_bend(event)` 之前添加：
```gdscript
"pitch_bend":
	pitch_bend_received.emit(event["channel"], event["value"])
	_process_pitch_bend(event)
```

**Step 3: 在 `_preprocess_events_up_to` 中也发射信号**

`_preprocess_events_up_to` 函数（约第 257 行）在 `seek` 和 `start_playback` 时被调用，需要同步发射信号以便监视器显示预处理状态。在 `control_change` 和 `pitch_bend` 分支也添加 emit：

```gdscript
elif event_type == "control_change":
	cc_received.emit(event["channel"], event["controller"], event["value"])
	_process_cc(event)
elif event_type == "pitch_bend":
	pitch_bend_received.emit(event["channel"], event["value"])
	_process_pitch_bend(event)
```

**Step 4: 验证**

在 Godot 编辑器中打开 demo 场景 `addons/clef/demo/midi_stream_player.tscn`，播放 MIDI，确认无报错。

**Step 5: Commit**

```
feat: add note_off/cc/pitch_bend/program_change signals to MidiStreamPlayer
```

---

### Task 2: 创建 ClefStationPlugin（EditorPlugin 主入口） — DONE

**Files:**
- Create: `addons/clef/editor/clef_station_plugin.gd`
- Modify: `addons/clef/plugin.gd:14-27` (`_enter_tree` / `_exit_tree`)

**Step 1: 创建 ClefStationPlugin**

```gdscript
## Clef Station 编辑器主屏幕插件
## 在 Godot 编辑器顶部标签栏添加 "Audio" 标签，与 2D/3D/Script 同级
@tool
class_name ClefStationPlugin
extends EditorPlugin

const MAIN_SCREEN_NAME: String = "Audio"

var _main_screen: Control = null


func _enter_tree() -> void:
	_main_screen = Control.new()
	_main_screen.name = "ClefStation"
	# 占位标签（后续替换为正式 UI）
	var label := Label.new()
	label.text = "Clef Station — Loading..."
	label.anchors_preset = Control.PRESET_CENTER
	_main_screen.add_child(label)
	add_child(_main_screen)


func _exit_tree() -> void:
	if _main_screen != null:
		remove_child(_main_screen)
		_main_screen.queue_free()
		_main_screen = null


func _has_main_screen() -> bool:
	return true


func _make_main_screen(visible: bool) -> Control:
	return _main_screen


func _get_plugin_name() -> String:
	return "Clef"


func _get_main_screen_icon() -> Texture2D:
	# 使用内置的 AudioStreamPlayer 图标作为占位
	return EditorInterface.get_editor_theme().get_icon("AudioStreamPlayer", "EditorIcons")
```

**Step 2: 在 plugin.gd 中注册 ClefStationPlugin**

修改 `addons/clef/plugin.gd`，在 `_enter_tree` 中添加主屏幕注册，在 `_exit_tree` 中清理：

```gdscript
# 新增成员变量
var _station_plugin: ClefStationPlugin

# _enter_tree 中添加（在 _register_project_settings() 之前）：
	_station_plugin = ClefStationPlugin.new()
	add_child(_station_plugin)

# _exit_tree 中添加（在最前面）：
	if _station_plugin != null:
		_station_plugin.queue_free()
		_station_plugin = null
```

**Step 3: 验证**

在 Godot 编辑器中重新加载插件（Project → Reload），确认顶部标签栏出现 "Audio" 标签，点击后显示占位界面。

**Step 4: Commit**

```
feat: add Clef Station editor main screen with Audio tab
```

---

### Task 3: 创建 ClefStation 主界面（三栏布局） — DONE

**Files:**
- Create: `addons/clef/editor/clef_station.gd`
- Modify: `addons/clef/editor/clef_station_plugin.gd`

**Step 1: 创建 ClefStation 主界面**

```gdscript
## Clef Station 主界面 — 三栏布局
## 左栏：音色浏览器 | 中栏：混音台 + 播放控制 | 右栏：MIDI 监视器
@tool
class_name ClefStation
extends Control

var _left_panel: PanelContainer
var _center_panel: PanelContainer
var _right_panel: PanelContainer
var _split_main: HSplitContainer
var _split_left: HSplitContainer


func _ready() -> void:
	anchors_preset = Control.PRESET_FULL_RECT
	_build_layout()


func _build_layout() -> void:
	_split_main = HSplitContainer.new()
	_split_main.name = "SplitMain"
	_split_main.anchors_preset = Control.PRESET_FULL_RECT
	_split_main.split_offset = 250
	add_child(_split_main)

	# 左栏：音色浏览器
	_left_panel = PanelContainer.new()
	_left_panel.name = "LeftPanel"
	_left_panel.min_size = Vector2i(200, 0)
	var left_label := Label.new()
	left_label.text = "Soundfont Browser"
	_left_panel.add_child(left_label)
	_split_main.add_child(_left_panel)

	# 中右分割
	_split_left = HSplitContainer.new()
	_split_left.name = "SplitLeft"
	_split_left.split_offset = -250
	_split_main.add_child(_split_left)

	# 中栏：混音台
	_center_panel = PanelContainer.new()
	_center_panel.name = "CenterPanel"
	_center_panel.min_size = Vector2i(300, 0)
	_center_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var center_label := Label.new()
	center_label.text = "Mixer & Transport"
	center_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	center_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_center_panel.add_child(center_label)
	_split_left.add_child(_center_panel)

	# 右栏：MIDI 监视器
	_right_panel = PanelContainer.new()
	_right_panel.name = "RightPanel"
	_right_panel.min_size = Vector2i(200, 0)
	var right_label := Label.new()
	right_label.text = "MIDI Monitor"
	_right_panel.add_child(right_label)
	_split_left.add_child(_right_panel)


## 切换左栏可见性
func set_left_panel_visible(visible: bool) -> void:
	_left_panel.visible = visible


## 切换右栏可见性
func set_right_panel_visible(visible: bool) -> void:
	_right_panel.visible = visible
```

**Step 2: 更新 ClefStationPlugin 使用 ClefStation**

替换 `clef_station_plugin.gd` 中的占位内容：

```gdscript
@tool
class_name ClefStationPlugin
extends EditorPlugin

const MAIN_SCREEN_NAME: String = "Audio"

var _main_screen: ClefStation = null


func _enter_tree() -> void:
	_main_screen = ClefStation.new()
	_main_screen.name = "ClefStation"
	add_child(_main_screen)


func _exit_tree() -> void:
	if _main_screen != null:
		remove_child(_main_screen)
		_main_screen.queue_free()
		_main_screen = null


func _has_main_screen() -> bool:
	return true


func _make_main_screen(visible: bool) -> Control:
	return _main_screen


func _get_plugin_name() -> String:
	return "Clef"


func _get_main_screen_icon() -> Texture2D:
	return EditorInterface.get_editor_theme().get_icon("AudioStreamPlayer", "EditorIcons")
```

**Step 3: 验证**

在 Godot 编辑器中重新加载插件，点击 "Audio" 标签，确认三栏布局显示，拖拽分割线可调整宽度。

**Step 4: Commit**

```
feat: implement Clef Station three-panel layout (Soundfont Browser / Mixer / MIDI Monitor)
```

---

### Task 4: 添加工具栏（左/右面板切换按钮） — DONE

**Files:**
- Modify: `addons/clef/editor/clef_station.gd`
- Modify: `addons/clef/editor/clef_station_plugin.gd`

**Step 1: 在 ClefStation 中添加工具栏**

在 `_build_layout` 中，在三栏布局之上添加 HBoxContainer 工具栏：

```gdscript
## 在 _build_layout 中，add_child(_split_main) 之前添加：
	var toolbar := HBoxContainer.new()
	toolbar.name = "Toolbar"
	toolbar.add_theme_constant_override("separation", 8)

	# 左栏切换按钮
	var btn_left := Button.new()
	btn_left.text = "SF2 Browser"
	btn_left.toggle_mode = true
	btn_left.button_pressed = true
	btn_left.tooltip_text = "Toggle Soundfont Browser panel"
	btn_left.toggled.connect(func(pressed: bool): set_left_panel_visible(pressed))
	toolbar.add_child(btn_left)

	# 右栏切换按钮
	var btn_right := Button.new()
	btn_right.text = "MIDI Monitor"
	btn_right.toggle_mode = true
	btn_right.button_pressed = true
	btn_right.tooltip_text = "Toggle MIDI Monitor panel"
	btn_right.toggled.connect(func(pressed: bool): set_right_panel_visible(pressed))
	toolbar.add_child(btn_right)

	# 弹簧
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	toolbar.add_child(spacer)

	add_child(toolbar)
```

注意：需要调整 `_split_main` 的布局，使其位于工具栏下方。在 `_ready` 中设置：

```gdscript
func _ready() -> void:
	anchors_preset = Control.PRESET_FULL_RECT
	_build_layout()
	# 将 _split_main 的 anchor 挪到工具栏下方
	# 使用 VBoxContainer 包裹更简洁，但为减少改动，直接调整 offset
```

**更简洁的做法** — 使用 VBoxContainer 包裹工具栏和分割区：

```gdscript
func _build_layout() -> void:
	var root := VBoxContainer.new()
	root.name = "Root"
	root.anchors_preset = Control.PRESET_FULL_RECT
	add_child(root)

	# 工具栏
	var toolbar := HBoxContainer.new()
	toolbar.name = "Toolbar"
	toolbar.add_theme_constant_override("separation", 8)
	toolbar.custom_minimum_size = Vector2i(0, 36)

	var btn_left := Button.new()
	btn_left.text = "SF2 Browser"
	btn_left.toggle_mode = true
	btn_left.button_pressed = true
	btn_left.tooltip_text = "Toggle Soundfont Browser panel"
	btn_left.toggled.connect(set_left_panel_visible)
	toolbar.add_child(btn_left)

	var btn_right := Button.new()
	btn_right.text = "MIDI Monitor"
	btn_right.toggle_mode = true
	btn_right.button_pressed = true
	btn_right.tooltip_text = "Toggle MIDI Monitor panel"
	btn_right.toggled.connect(set_right_panel_visible)
	toolbar.add_child(btn_right)

	root.add_child(toolbar)

	# 三栏分割
	_split_main = HSplitContainer.new()
	_split_main.name = "SplitMain"
	_split_main.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_split_main.split_offset = 250
	root.add_child(_split_main)

	# ... 后续左/中/右面板代码不变
```

**Step 2: 验证**

确认工具栏显示两个切换按钮，点击可隐藏/显示左右面板。

**Step 3: Commit**

```
feat: add Clef Station toolbar with panel toggle buttons
```

---

### Task 5: 暴露 MidiStreamPlayer 引用给编辑器 — DONE

**Files:**
- Create: `addons/clef/editor/clef_station_editor_bridge.gd`

**Step 1: 创建编辑器桥接单例**

ClefStation 需要在编辑器运行时找到场景中的 MidiStreamPlayer 实例。创建一个 Autoload 单例作为桥接：

```gdscript
## 编辑器与运行时 MidiStreamPlayer 的桥接
## Autoload 单例，在编辑器中持有当前选中/预览的 MidiStreamPlayer 引用
## 仅在编辑器模式下活跃
extends Node

signal player_changed(player: MidiStreamPlayer)
signal player_connected(player: MidiStreamPlayer)
signal player_disconnected(player: MidiStreamPlayer)

var current_player: MidiStreamPlayer = null : set = set_current_player

var _connected_players: Array[MidiStreamPlayer] = []


func set_current_player(player: MidiStreamPlayer) -> void:
	if current_player == player:
		return
	_disconnect_current()
	current_player = player
	player_changed.emit(player)
	if player != null:
		_connect_player(player)


func _connect_player(player: MidiStreamPlayer) -> void:
	if player in _connected_players:
		return
	player.note_triggered.connect(_on_note_triggered)
	player.note_released.connect(_on_note_released)
	player.cc_received.connect(_on_cc_received)
	player.pitch_bend_received.connect(_on_pitch_bend_received)
	player.program_changed.connect(_on_program_changed)
	_connected_players.append(player)
	player_connected.emit(player)


func _disconnect_current() -> void:
	if current_player != null:
		_disconnect_player(current_player)


func _disconnect_player(player: MidiStreamPlayer) -> void:
	if player not in _connected_players:
		return
	if player.note_triggered.is_connected(_on_note_triggered):
		player.note_triggered.disconnect(_on_note_triggered)
	if player.note_released.is_connected(_on_note_released):
		player.note_released.disconnect(_on_note_released)
	if player.cc_received.is_connected(_on_cc_received):
		player.cc_received.disconnect(_on_cc_received)
	if player.pitch_bend_received.is_connected(_on_pitch_bend_received):
		player.pitch_bend_received.disconnect(_on_pitch_bend_received)
	if player.program_changed.is_connected(_on_program_changed):
		player.program_changed.disconnect(_on_program_changed)
	_connected_players.erase(player)
	player_disconnected.emit(player)


## 信号转发（供面板连接）
signal midi_note_on(channel: int, pitch: int, velocity: int)
signal midi_note_off(channel: int, pitch: int)
signal midi_cc(channel: int, controller: int, value: int)
signal midi_pitch_bend(channel: int, value: int)
signal midi_program_change(channel: int, preset_index: int)


func _on_note_triggered(ch: int, pitch: int, vel: int) -> void:
	midi_note_on.emit(ch, pitch, vel)


func _on_note_released(ch: int, pitch: int) -> void:
	midi_note_off.emit(ch, pitch)


func _on_cc_received(ch: int, ctrl: int, val: int) -> void:
	midi_cc.emit(ch, ctrl, val)


func _on_pitch_bend_received(ch: int, val: int) -> void:
	midi_pitch_bend.emit(ch, val)


func _on_program_changed(ch: int, preset: int) -> void:
	midi_program_change.emit(ch, preset)
```

**注意：** 此桥接单例暂不注册为 Autoload（Autoload 需要项目设置，Phase 1 先作为插件内部子节点管理）。在 `ClefStationPlugin._enter_tree` 中创建：

```gdscript
var _bridge: Node = null

func _enter_tree() -> void:
	_bridge = preload("res://addons/clef/editor/clef_station_editor_bridge.gd").new()
	_bridge.name = "ClefEditorBridge"
	EditorInterface.get_base_control().add_child(_bridge)
	# ... existing _main_screen creation
```

**Step 2: Commit**

```
feat: add editor bridge for MidiStreamPlayer signal forwarding
```

---

## 验收标准

Phase 1 完成后应满足：

1. Godot 编辑器顶部标签栏出现 "Clef" 标签（带 AudioStreamPlayer 图标） ✅
2. 点击 "Clef" 显示三栏布局（左：SF2 Browser 占位、中：Mixer 占位、右：MIDI Monitor 占位） ✅
3. 工具栏两个切换按钮可隐藏/显示左右面板 ✅
4. 拖拽分割线可调整面板宽度 ✅
5. MidiStreamPlayer 新增 4 个信号，在 demo 场景播放时无报错 ✅
6. EditorBridge 单例可转发 MidiStreamPlayer 信号 ✅

## 实现笔记

### 与计划的偏差

1. **API 修正**：计划中使用 `_make_main_screen()`，实际 Godot 4.6 正确 API 是 `_make_visible()` + `EditorInterface.get_editor_main_screen().add_child()`
2. **架构简化**：取消了独立的 `ClefStationPlugin`（EditorPlugin），直接在 `plugin.gd` 中实现 `_has_main_screen()` / `_make_visible()`，避免 Godot 不支持嵌套 EditorPlugin 的问题
3. **布局构建时机**：从 `_init()` 改为 `_ready()`，确保控件在场景树中时才构建子节点，`anchors` 才能正确设置
4. **`_setup_audio_buses` bug 修复**：原代码 `AudioServer.get_bus_index("ClefMaster")` 返回值未保存到 `_clef_master_bus_idx`，导致重复创建总线

## 文件清单

| 操作 | 文件 |
|------|------|
| 修改 | `addons/clef/player/midi_stream_player.gd` |
| 修改 | `addons/clef/plugin.gd` |
| 新建 | `addons/clef/editor/clef_station.gd` |
| 新建 | `addons/clef/editor/clef_station_editor_bridge.gd` |
