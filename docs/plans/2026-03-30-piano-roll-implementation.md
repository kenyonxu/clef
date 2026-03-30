# Piano Roll Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 Clef Station 中栏新增实时钢琴卷帘面板，播放时可视化音符分布并支持点击跳转。

**Architecture:** 新增 `PianoRoll` Control，通过 `set_notes()` 接收预处理后的音符数组，在 `_draw()` 中批量绘制。ClefStation 在 MIDI 加载时从 MidiResource 提取音符并传递，播放时每帧更新位置。

**Tech Stack:** GDScript, Godot 4.6, Control._draw() API

---

### Task 1: PianoRoll 骨架

**Files:**
- Create: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: 创建文件并定义数据结构和基本框架**

```gdscript
## 钢琴卷帘 — 实时音符可视化
@tool
class_name PianoRoll
extends Control

signal seek_requested(position: float)

## 内部音符数据（预处理，不依赖 MidiResource）
class RollNote:
    var channel: int
    var pitch: int
    var start_time: float  # 秒
    var duration: float    # 秒
    var velocity: int

    func _init(ch: int, p: int, st: float, dur: float, vel: int) -> void:
        channel = ch
        pitch = p
        start_time = st
        duration = dur
        velocity = vel


## 通道颜色（与 MidiMonitor 一致）
const _CHANNEL_COLORS: Array[Color] = [
    Color(0.4, 1.0, 0.4),   # Ch 0  绿
    Color(0.4, 0.7, 1.0),   # Ch 1  蓝
    Color(1.0, 0.7, 0.3),   # Ch 2  橙
    Color(0.9, 0.5, 0.9),   # Ch 3  紫
    Color(1.0, 0.5, 0.5),   # Ch 4  红
    Color(0.5, 0.9, 0.9),   # Ch 5  青
    Color(1.0, 1.0, 0.4),   # Ch 6  黄
    Color(0.7, 0.5, 1.0),   # Ch 7  淡紫
    Color(0.6, 1.0, 0.6),   # Ch 8  浅绿
    Color(0.5, 0.8, 1.0),   # Ch 9  浅蓝（鼓）
    Color(1.0, 0.6, 0.6),   # Ch 10 浅红
    Color(0.6, 0.9, 0.7),   # Ch 11
    Color(0.8, 0.7, 0.5),   # Ch 12
    Color(0.7, 0.7, 0.9),   # Ch 13
    Color(0.9, 0.8, 0.6),   # Ch 14
    Color(0.8, 0.8, 0.8),   # Ch 15 灰
]

var _notes: Array[RollNote] = []
var _duration: float = 0.0
var _playback_position: float = 0.0
var _pixels_per_second: float = 100.0
var _pixels_per_note: float = 4.0
var _min_pitch: int = 60
var _max_pitch: int = 72


func _ready() -> void:
    custom_minimum_size = Vector2i(0, 160)
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    size_flags_vertical = Control.SIZE_EXPAND_FILL
    mouse_default_cursor_shape = Control.CURSOR_IBEAM


func set_notes(notes: Array[RollNote], duration: float) -> void:
    _notes = notes
    _duration = duration
    _recalc_layout()
    queue_redraw()


func set_playback_position(position: float) -> void:
    _playback_position = position
    queue_redraw()


func clear_notes() -> void:
    _notes.clear()
    _duration = 0.0
    _playback_position = 0.0
    _min_pitch = 60
    _max_pitch = 72
    queue_redraw()


func _recalc_layout() -> void:
    if _notes.is_empty():
        return
    # 计算音域范围（留 1 八度余量）
    var lo: int = 127
    var hi: int = 0
    for note in _notes:
        if note.pitch < lo:
            lo = note.pitch
        if note.pitch > hi:
            hi = note.pitch
    _min_pitch = maxi(0, lo - 12)
    _max_pitch = mini(127, hi + 12)
    # 计算 pixels_per_second：让整首曲子铺满可视宽度
    var avail_width: float = size.x
    if avail_width > 0 and _duration > 0:
        _pixels_per_second = avail_width / _duration
    # 计算 pixels_per_note：根据可用高度
    var note_range: int = _max_pitch - _min_pitch + 1
    var avail_height: float = size.y
    if avail_height > 0 and note_range > 0:
        _pixels_per_note = avail_height / float(note_range)


func _draw() -> void:
    var w := size.x
    var h := size.y
    if w <= 0 or h <= 0:
        return
    # 背景
    draw_rect(Rect2(Vector2.ZERO, Vector2(w, h)), Color(0.06, 0.06, 0.09))


func _gui_input(event: InputEvent) -> void:
    if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
        var time := _pixel_to_time(event.position.x)
        if time >= 0.0 and time <= _duration:
            seek_requested.emit(time)


func _time_to_x(t: float) -> float:
    return t * _pixels_per_second


func _pixel_to_time(px: float) -> float:
    return px / _pixels_per_second


func _pitch_to_y(pitch: int) -> float:
    return (_max_pitch - pitch) * _pixels_per_note


func _y_to_pitch(py: float) -> int:
    return _max_pitch - int(py / _pixels_per_note)
```

**Step 2: 在 Godot 编辑器中验证**

- 打开 Godot 编辑器，确认 Clef Station 正常加载无报错
- PianoRoll 尚未集成，此步仅确认文件无语法错误

**Step 3: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add PianoRoll skeleton with data types and coordinate mapping"
```

---

### Task 2: 音符绘制 + 背景网格

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd` — `_draw()` 方法

**Step 1: 实现 _draw() 中的网格和音符绘制**

替换 `_draw()` 方法体：

```gdscript
func _draw() -> void:
    var w := size.x
    var h := size.y
    if w <= 0 or h <= 0:
        return

    # 背景
    draw_rect(Rect2(Vector2.ZERO, Vector2(w, h)), Color(0.06, 0.06, 0.09))

    if _notes.is_empty():
        # 无数据时显示占位文字
        draw_string(
            ThemeDB.fallback_font,
            Vector2(8, 16),
            "Load a MIDI file to view piano roll",
            HORIZONTAL_ALIGNMENT_LEFT, w - 16, 14,
            Color(0.3, 0.3, 0.35)
        )
        return

    # ── 八度分隔线 ──
    var grid_color := Color(0.12, 0.12, 0.16)
    var octave_color := Color(0.18, 0.18, 0.22)
    for pitch in range(_min_pitch, _max_pitch + 1):
        var y := _pitch_to_y(pitch)
        var c := grid_color
        if pitch % 12 == 0:  # C 音
            c = octave_color
        draw_line(Vector2(0, y), Vector2(w, y), c, 1.0)

    # ── 音符块 ──
    for note in _notes:
        var x := _time_to_x(note.start_time)
        var nw := note.duration * _pixels_per_second
        var y := _pitch_to_y(note.pitch + 1)  # +1 因为 pitch_to_y 返回顶部
        var nh := _pixels_per_note - 1.0

        # 通道颜色 × 力度亮度
        var base_color: Color = _CHANNEL_COLORS[note.channel % _CHANNEL_COLORS.size()]
        var brightness := 0.5 + float(note.velocity) / 127.0 * 0.5
        var color := Color(
            base_color.r * brightness,
            base_color.g * brightness,
            base_color.b * brightness
        )
        draw_rect(Rect2(Vector2(x, y), Vector2(nw, nh)), color)
```

**Step 2: 手动测试 — 添加测试数据验证绘制**

在 ClefStation 临时连接测试（加载 MIDI 后验证音符是否正确显示）。

**Step 3: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): implement note rendering and octave grid"
```

---

### Task 3: 播放线

**Files:**
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd` — `_draw()` 追加播放线

**Step 1: 在 _draw() 末尾添加播放线绘制**

在 `_draw()` 方法的音符绘制之后追加：

```gdscript
    # ── 播放位置线 ──
    if _playback_position > 0.0 and _duration > 0.0:
        var px := _time_to_x(_playback_position)
        draw_line(Vector2(px, 0), Vector2(px, h), Color(1.0, 1.0, 1.0, 0.8), 2.0)
```

**Step 2: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd
git commit -m "feat(piano-roll): add playback position line"
```

---

### Task 4: EditorPlayer 暴露 MidiResource

**Files:**
- Modify: `addons/clef/editor/editor_player/editor_player.gd`

**Step 1: 添加 get_midi_resource() 方法**

在 `get_duration()` 方法之后添加：

```gdscript
func get_midi_resource() -> MidiResource:
    if _player == null:
        return null
    return _player.midi_resource
```

**Step 2: Commit**

```bash
git add addons/clef/editor/editor_player/editor_player.gd
git commit -m "feat(editor-player): expose get_midi_resource() for PianoRoll integration"
```

---

### Task 5: 集成到 ClefStation

**Files:**
- Modify: `addons/clef/editor/clef_station.gd`

**Step 1: 添加 preload 和变量**

在文件顶部的 preload 区域添加：
```gdscript
const PianoRoll = preload("res://addons/clef/editor/piano_roll/piano_roll.gd")
```

在变量区域添加：
```gdscript
var _piano_roll: PianoRoll
```

**Step 2: 在 _build_layout() 中创建 PianoRoll**

在 `center_vbox.add_child(_transport_bar)` 之后、`_mini_mixer = MiniMixer.new()` 之前插入：

```gdscript
    _piano_roll = PianoRoll.new()
    _piano_roll.seek_requested.connect(func(pos: float):
        _editor_player.seek(pos)
    )
    center_vbox.add_child(_piano_roll)
```

**Step 3: 添加音符提取方法**

在类中添加新方法：

```gdscript
func _update_piano_roll() -> void:
    var midi_res: MidiResource = _editor_player.get_midi_resource()
    if midi_res == null or midi_res.tracks.is_empty():
        _piano_roll.clear_notes()
        return
    var roll_notes: Array[PianoRoll.RollNote] = []
    var ticks_per_second: float = float(midi_res.tempo) / 60.0 * float(midi_res.timebase)
    if ticks_per_second <= 0.0:
        return
    for track in midi_res.tracks:
        for note in track.notes:
            var start_time: float = float(note.start_ticks) / ticks_per_second
            var duration: float = float(note.duration_ticks) / ticks_per_second
            roll_notes.append(PianoRoll.RollNote.new(
                track.channel, note.pitch, start_time, duration, note.velocity
            ))
    var duration: float = _editor_player.get_duration()
    _piano_roll.set_notes(roll_notes, duration)
```

**Step 4: 连接信号**

在 `_init_editor_player()` 方法中，连接 `file_loaded` 信号：

```gdscript
func _init_editor_player() -> void:
    _editor_player = EditorPlayer.new()
    _editor_player.setup(self, _bridge)
    _editor_player.file_loaded.connect(func(_path: String, _dur: float):
        _update_piano_roll()
    )
    _wire_transport()
    _wire_mixer()
```

**Step 5: 在 _update_progress() 中更新播放位置**

在 `_update_progress()` 方法中，在更新 TransportBar 之后添加：

```gdscript
    _piano_roll.set_playback_position(_editor_player.get_position())
```

**Step 6: 在 _recalc_layout 中响应 resize**

在 PianoRoll 中添加 `_notification` 处理：

```gdscript
func _notification(what: int) -> void:
    if what == NOTIFICATION_RESIZED and not _notes.is_empty():
        _recalc_layout()
        queue_redraw()
```

**Step 7: 在 Godot 编辑器中验证**

- 打开 Clef Station，加载一个 MIDI 文件
- 确认 PianoRoll 显示音符块
- 播放时确认白色播放线跟随移动
- 点击 PianoRoll 确认跳转功能

**Step 8: Commit**

```bash
git add addons/clef/editor/piano_roll/piano_roll.gd addons/clef/editor/editor_player/editor_player.gd addons/clef/editor/clef_station.gd
git commit -m "feat(piano-roll): integrate PianoRoll into ClefStation with note extraction and seek"
```

---

### Task 6: 更新文档

**Files:**
- Modify: `addons/clef/README.md`
- Modify: `addons/clef/docs/user_guide.md`

**Step 1: 在 README 中栏描述中添加 PianoRoll**

在"中栏：播放控制 + 混音台"章节的传输控制栏和迷你混音台之间添加钢琴卷帘说明。

**Step 2: 在 user_guide.md 的 4.1 节添加 PianoRoll 说明**

**Step 3: Commit**

```bash
git add addons/clef/README.md addons/clef/docs/user_guide.md
git commit -m "docs: add piano roll to README and user guide"
```

---

## 关键注意事项

- GDScript 文件使用 Write 工具而非 Edit（tab/space 匹配问题）
- `@tool` 脚本中不可用 BBCode，用 `draw_string()` 绘制文字
- `MidiResource` 的 ticks → seconds 转换公式：`seconds = ticks / (tempo / 60.0 * timebase)`
- `_recalc_layout()` 在 `NOTIFICATION_RESIZED` 时重新计算，确保窗口大小变化后布局正确
- 鼓组（Channel 9）的音符通常很短（单 tick），绘制时最小宽度限制为 2px 避免不可见
