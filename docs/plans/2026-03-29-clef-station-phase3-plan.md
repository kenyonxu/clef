# Clef Station Phase 3 — MIDI Monitor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现右栏 MIDI 监视器面板，实时显示 MidiStreamPlayer 事件流，支持按通道/类型过滤、颜色编码、自动滚动、活跃音符统计。

**Architecture:** 新建 `MidiMonitor` 控件替换右栏占位。通过 `ClefStationEditorBridge` 的转发信号接收 MIDI 事件（note_on/off/cc/pitch_bend/program_change），在 `RichTextLabel` 或 `Tree` 中实时追加彩色事件行。`plugin.gd` 将 bridge 引用传递给 `ClefStation`，再传递给 `MidiMonitor`。

**Tech Stack:** GDScript, RichTextLabel（事件流）, HBoxContainer（过滤工具栏）, Label（统计栏）, Timer（事件率计算）

---

### Task 1: 传递 Bridge 引用到 ClefStation

**Files:**
- Modify: `addons/clef/plugin.gd:30-33` (bridge 和 main_screen 创建)
- Modify: `addons/clef/editor/clef_station.gd:7-15` (成员变量)

**Step 1: 在 ClefStation 添加 bridge 成员和 setter**

在 `clef_station.gd` 成员变量区添加：

```gdscript
var _bridge: RefCounted = null


func set_bridge(bridge: RefCounted) -> void:
	_bridge = bridge
```

**Step 2: 在 plugin.gd 中传递 bridge 给 ClefStation**

在 `_enter_tree()` 中，创建 bridge 之后、`_make_visible(false)` 之前添加：

```gdscript
_main_screen.set_bridge(_bridge)
```

**Step 3: 验证**

重新加载 Godot 编辑器，确认无报错，Clef Station 正常显示。

**Step 4: Commit**

```
feat: pass editor bridge reference to ClefStation
```

---

### Task 2: 创建 MidiMonitor 控件

**Files:**
- Create: `addons/clef/editor/midi_monitor/midi_monitor.gd`

**Step 1: 创建 MidiMonitor 基础框架**

```gdscript
## MIDI 监视器面板 — 实时事件流 + 过滤 + 统计
@tool
class_name MidiMonitor
extends VBoxContainer

## 事件类型
enum EventType {
	NOTE_ON,
	NOTE_OFF,
	CC,
	PITCH_BEND,
	PROGRAM_CHANGE,
}

## 事件数据
class MidiEvent:
	var type: int
	var channel: int
	var data1: int  ## pitch / controller / preset
	var data2: int  ## velocity / value / null
	var timestamp: float

	func _init(t: int, ch: int, d1: int, d2: int = 0) -> void:
		type = t
		channel = ch
		data1 = d1
		data2 = d2
		timestamp = Time.get_ticks_msec() / 1000.0


## 事件颜色（按类型）
const _EVENT_COLORS: Dictionary = {
	EventType.NOTE_ON: Color(0.4, 1.0, 0.4),
	EventType.NOTE_OFF: Color(0.6, 0.6, 0.6),
	EventType.CC: Color(0.4, 0.7, 1.0),
	EventType.PITCH_BEND: Color(1.0, 0.7, 0.3),
	EventType.PROGRAM_CHANGE: Color(0.9, 0.5, 0.9),
}

const _EVENT_NAMES: Dictionary = {
	EventType.NOTE_ON: "NoteOn",
	EventType.NOTE_OFF: "NoteOff",
	EventType.CC: "CC",
	EventType.PITCH_BEND: "PB",
	EventType.PROGRAM_CHANGE: "PC",
}

const MAX_EVENTS: int = 500

var _event_log: RichTextLabel
var _stats_label: Label
var _events: Array[MidiEvent] = []
var _active_notes: int = 0
var _event_count: int = 0
var _filter_channel: int = -1  ## -1 = 全部
var _filter_types: int = 0x1F  ## 全部类型启用
var _auto_scroll: bool = true
var _rate_timer: Timer = null
var _rate_count: int = 0


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_build_ui()


func _build_ui() -> void:
	# 过滤工具栏
	var toolbar := HBoxContainer.new()
	toolbar.add_theme_constant_override("separation", 4)
	toolbar.custom_minimum_size = Vector2i(0, 28)

	var ch_label := Label.new()
	ch_label.text = "Ch:"
	toolbar.add_child(ch_label)

	var ch_btn := Button.new()
	ch_btn.text = "All"
	ch_btn.custom_minimum_size = Vector2i(36, 0)
	ch_btn.toggle_mode = true
	ch_btn.button_pressed = true
	ch_btn.tooltip_text = "Channel filter"
	ch_btn.pressed.connect(_on_channel_filter_pressed)
	toolbar.add_child(ch_btn)

	# 类型过滤按钮（复用同一个按钮循环创建）
	for type_key in [EventType.NOTE_ON, EventType.CC, EventType.PITCH_BEND, EventType.PROGRAM_CHANGE]:
		var btn := Button.new()
		btn.text = _EVENT_NAMES[type_key]
		btn.custom_minimum_size = Vector2i(40, 0)
		btn.toggle_mode = true
		btn.button_pressed = true
		btn.tooltip_text = "Toggle %s filter" % _EVENT_NAMES[type_key]
		btn.pressed.connect(_on_type_filter_pressed.bind(type_key, btn))
		toolbar.add_child(btn)

	var scroll_btn := Button.new()
	scroll_btn.text = "Auto"
	scroll_btn.custom_minimum_size = Vector2i(36, 0)
	scroll_btn.toggle_mode = true
	scroll_btn.button_pressed = true
	scroll_btn.tooltip_text = "Toggle auto-scroll"
	scroll_btn.pressed.connect(func(pressed: bool): _auto_scroll = pressed)
	toolbar.add_child(scroll_btn)

	var clear_btn := Button.new()
	clear_btn.text = "Clear"
	clear_btn.custom_minimum_size = Vector2i(36, 0)
	clear_btn.tooltip_text = "Clear event log"
	clear_btn.pressed.connect(_clear_log)
	toolbar.add_child(clear_btn)

	add_child(toolbar)

	# 事件流
	_event_log = RichTextLabel.new()
	_event_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_event_log.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_event_log.scroll_following = true
	_event_log.bbcode_enabled = true
	_event_log.fit_content = true
	_event_log.add_theme_constant_override("line_separation", 1)
	add_child(_event_log)

	# 统计栏
	var stats_container := PanelContainer.new()
	stats_container.custom_minimum_size = Vector2i(0, 22)
	var stats_style := StyleBoxFlat.new()
	stats_style.bg_color = Color(0.08, 0.08, 0.12)
	stats_style.set_content_margin_all(4)
	stats_container.add_theme_stylebox_override("panel", stats_style)
	_stats_label = Label.new()
	_stats_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	stats_container.add_child(_stats_label)
	add_child(stats_container)

	# 事件率定时器（每秒统计）
	_rate_timer = Timer.new()
	_rate_timer.wait_time = 1.0
	_rate_timer.timeout.connect(_update_rate)
	add_child(_rate_timer)
	_rate_timer.start()


func connect_bridge(bridge: RefCounted) -> void:
	if bridge == null:
		return
	if "midi_note_on" in bridge:
		bridge.midi_note_on.connect(_on_midi_note_on)
	if "midi_note_off" in bridge:
		bridge.midi_note_off.connect(_on_midi_note_off)
	if "midi_cc" in bridge:
		bridge.midi_cc.connect(_on_midi_cc)
	if "midi_pitch_bend" in bridge:
		bridge.midi_pitch_bend.connect(_on_midi_pitch_bend)
	if "midi_program_change" in bridge:
		bridge.midi_program_change.connect(_on_midi_program_change)


# ─── 事件接收 ──────────────────────────────────────────

func _on_midi_note_on(ch: int, pitch: int, vel: int) -> void:
	_append_event(MidiEvent.new(EventType.NOTE_ON, ch, pitch, vel))
	_active_notes += 1
	_rate_count += 1


func _on_midi_note_off(ch: int, pitch: int) -> void:
	_append_event(MidiEvent.new(EventType.NOTE_OFF, ch, pitch, 0))
	_active_notes = maxi(0, _active_notes - 1)
	_rate_count += 1


func _on_midi_cc(ch: int, controller: int, value: int) -> void:
	_append_event(MidiEvent.new(EventType.CC, ch, controller, value))
	_rate_count += 1


func _on_midi_pitch_bend(ch: int, value: int) -> void:
	_append_event(MidiEvent.new(EventType.PITCH_BEND, ch, value, 0))
	_rate_count += 1


func _on_midi_program_change(ch: int, preset: int) -> void:
	_append_event(MidiEvent.new(EventType.PROGRAM_CHANGE, ch, preset, 0))
	_rate_count += 1


# ─── 事件渲染 ──────────────────────────────────────────

func _append_event(evt: MidiEvent) -> void:
	_events.append(evt)
	if _events.size() > MAX_EVENTS:
		_events.pop_front()
		_event_log.clear()
		_rebuild_log()
		return
	_append_event_line(evt)


func _append_event_line(evt: MidiEvent) -> void:
	if not _passes_filter(evt):
		return
	var color: Color = _EVENT_COLORS.get(evt.type, Color(1, 1, 1))
	var text := _format_event(evt)
	_event_log.append_text("[color #%s]%s[/color]\n" % [color.to_html(false), text])
	if _auto_scroll:
		_event_log.scroll_to_line(_event_log.get_line_count() - 1)


func _format_event(evt: MidiEvent) -> String:
	match evt.type:
		EventType.NOTE_ON:
			return "Ch%-2d NoteOn  %-3d vel:%-3d" % [evt.channel, evt.data1, evt.data2]
		EventType.NOTE_OFF:
			return "Ch%-2d NoteOff %-3d" % [evt.channel, evt.data1]
		EventType.CC:
			return "Ch%-2d CC#%-3d val:%-3d" % [evt.channel, evt.data1, evt.data2]
		EventType.PITCH_BEND:
			return "Ch%-2d PitchBend %-5d" % [evt.channel, evt.data1]
		EventType.PROGRAM_CHANGE:
			return "Ch%-2d PC      %-3d" % [evt.channel, evt.data1]
		_:
			return "Ch%-2d ????" % evt.channel


func _rebuild_log() -> void:
	for evt in _events:
		_append_event_line(evt)


# ─── 过滤 ──────────────────────────────────────────────

func _passes_filter(evt: MidiEvent) -> bool:
	if _filter_channel >= 0 and evt.channel != _filter_channel:
		return false
	if not (_filter_types & (1 << evt.type)):
		return false
	return true


func _on_channel_filter_pressed() -> void:
	_filter_channel = -1  ## 暂时只支持 All，后续可改为下拉选择


func _on_type_filter_pressed(type_val: int, btn: Button) -> void:
	if btn.button_pressed:
		_filter_types |= (1 << type_val)
	else:
		_filter_types &= ~(1 << type_val)
	_event_log.clear()
	_rebuild_log()


# ─── 统计 ──────────────────────────────────────────────

func _update_rate() -> void:
	_stats_label.text = "Events: %d | Active notes: %d | Rate: %d/s" % [_event_count, _active_notes, _rate_count]
	_rate_count = 0


func _clear_log() -> void:
	_events.clear()
	_active_notes = 0
	_event_count = 0
	_event_log.clear()
	_update_rate()
```

**Step 2: Commit**

```
feat: add MidiMonitor panel with event log, filtering, and statistics
```

---

### Task 3: 集成 MidiMonitor 到 ClefStation

**Files:**
- Modify: `addons/clef/editor/clef_station.gd`

**Step 1: 添加 preload 和成员变量**

在文件顶部（SoundfontBrowser preload 下方）添加：

```gdscript
const MidiMonitor = preload("res://addons/clef/editor/midi_monitor/midi_monitor.gd")
```

在成员变量区添加：

```gdscript
var _midi_monitor: MidiMonitor
```

**Step 2: 替换右栏占位**

在 `_build_layout()` 中，替换右栏 PanelContainer 的 Label 占位为 MidiMonitor：

```gdscript
	# 右栏：MIDI 监视器
	_right_panel = PanelContainer.new()
	_right_panel.name = "RightPanel"
	_right_panel.custom_minimum_size = Vector2i(180, 0)
	_right_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_style_panel(_right_panel, Color(0.14, 0.10, 0.10))
	_midi_monitor = MidiMonitor.new()
	_right_panel.add_child(_midi_monitor)
	split_right.add_child(_right_panel)
```

**Step 3: 在 set_bridge 中连接 MidiMonitor**

修改 `set_bridge()` 方法：

```gdscript
func set_bridge(bridge: RefCounted) -> void:
	_bridge = bridge
	if _midi_monitor != null:
		_midi_monitor.connect_bridge(_bridge)
```

注意：`set_bridge` 在 `plugin.gd._enter_tree()` 中调用时，`_midi_monitor` 可能还未创建（因为 `_build_layout()` 在 `_ready()` 中）。需要在 `_build_layout()` 末尾补充连接：

```gdscript
	# 在 _build_layout() 末尾添加
	if _bridge != null and _midi_monitor != null:
		_midi_monitor.connect_bridge(_bridge)
```

**Step 4: 验证**

重新加载 Godot 编辑器，确认右栏显示 MidiMonitor 面板（工具栏 + 空白事件流 + 统计栏），无报错。

**Step 5: Commit**

```
feat: integrate MidiMonitor into ClefStation right panel
```

---

### Task 4: 验证与修复

**Files:**
- Modify: `addons/clef/editor/midi_monitor/midi_monitor.gd`

**Step 1: 验证事件接收**

需要在运行时连接 MidiStreamPlayer 到 bridge 才能接收事件。当前 bridge 的 `set_current_player()` 尚未被调用。

临时方案：在 `plugin.gd` 中添加调试代码，在编辑器场景树中查找 MidiStreamPlayer 并连接。

在 `plugin.gd._enter_tree()` 末尾添加（仅用于验证）：

```gdscript
	# 延迟查找场景中的 MidiStreamPlayer（调试用）
	await get_tree().create_timer(2.0).timeout
	_connect_scene_player()


func _connect_scene_player() -> void:
	var scene_root := EditorInterface.get_edited_scene_root()
	if scene_root == null:
		return
	var players := scene_root.find_children("*", "MidiStreamPlayer", true, false)
	if players.is_empty():
		return
	_bridge.set_current_player(players[0])
	print("[ClefPlugin] Connected player: %s" % players[0].name)
```

**Step 2: 验证**

1. 打开包含 MidiStreamPlayer 的场景（如 `addons/clef/demo/midi_stream_player.tscn`）
2. 运行场景（F6）
3. 播放 MIDI 文件
4. 切换到 Clef 标签，确认事件流实时更新
5. 确认过滤按钮工作（取消勾选某类型，事件流刷新）
6. 确认 Clear 按钮清空事件流
7. 确认统计栏显示活跃音符数和事件率

**Step 3: Commit**

```
feat: auto-connect scene MidiStreamPlayer to bridge for monitor
```

---

### Task 5: UI 打磨

**Files:**
- Modify: `addons/clef/editor/midi_monitor/midi_monitor.gd`

**Step 1: 优化 RichTextLabel 性能**

当事件过多时，逐行追加会导致 BBCode 解析变慢。改为固定缓冲区：

在 `_append_event()` 中，当事件超过 MAX_EVENTS 时使用 `clear()` + `_rebuild_log()` 已经处理了。但可以优化 `_rebuild_log()` 避免全量重建——实际上 clear+rebuild 已经是标准做法，无需额外优化。

**Step 2: 添加 MIDI 停止时自动清理活跃音符**

监听 bridge 的 `player_changed` 信号，当 player 停止时重置统计：

```gdscript
func connect_bridge(bridge: RefCounted) -> void:
	# ... existing signal connections ...
	if "player_changed" in bridge:
		bridge.player_changed.connect(func(player):
			if player == null:
				_active_notes = 0
		)
```

**Step 3: 优化按钮尺寸**

过滤按钮文字可能显示不全，调整最小宽度：

```
NOTE_ON 按钮最小宽度 50px，CC 36px，PB 36px，PC 36px
```

**Step 4: Commit**

```
fix: polish MidiMonitor UI and add player disconnect cleanup
```

---

## 验收标准

Phase 3 完成后应满足：

1. 右栏显示 MIDI Monitor 面板（过滤工具栏 + 事件流 + 统计栏）
2. ~~运行场景播放 MIDI 时，事件流实时显示彩色事件~~ → **延后到 Phase 4**
3. NoteOn 绿色、NoteOff 灰色、CC 蓝色、PitchBend 橙色、PC 紫色
4. 过滤按钮可按类型过滤事件
5. Auto 按钮切换自动滚动
6. Clear 按钮清空事件流
7. 统计栏显示事件总数、活跃音符数、事件率
8. 切换标签/重新加载插件无报错

## 实现笔记

### 与计划的偏差

1. **Task 4 事件验证延后**：原计划通过 bridge 连接运行时场景中的 MidiStreamPlayer 来验证事件流，但这要求运行场景才能工作。改为先完成 UI 面板，事件流验证延后到 Phase 4（编辑器播放器）完成后再串联
2. **架构决策**：MidiMonitor 的事件数据源应为编辑器级别的 MIDI 播放器（中栏 Mixer & Transport），而非运行时场景中的 MidiStreamPlayer。编辑器播放器将在 Phase 4 中实现，届时 bridge 需要连接到编辑器播放器而非场景 player

## 文件清单

| 操作 | 文件 |
|------|------|
| 新建 | `addons/clef/editor/midi_monitor/midi_monitor.gd` |
| 修改 | `addons/clef/editor/clef_station.gd` |
| 修改 | `addons/clef/plugin.gd` |
