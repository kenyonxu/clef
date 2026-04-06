# Piano Roll 编辑功能增强设计

> 日期：2026-04-06
> 状态：已确认

## 目标

为 Piano Roll 添加四项编辑功能：轨道管理（音色切换+新增轨道）、音符创建、复制粘贴。

## 当前状态

- Piano Roll 为纯代码绘制的 Control（~1100行），无 .tscn
- 内部 `RollNote`（channel/pitch/start_time/duration/velocity）存储音符
- 已有：选择、拖动移动、拖动调整时长、删除、撤销/重做
- Legend bar（28px）纯绘制，显示 `Ch{N} {乐器名}`，无交互
- `ADD_NOTE` 子模式为半成品（创建临时音符但无法提交）
- 无复制粘贴功能
- 音符重叠完全允许，无冲突检测

## 一、轨道管理（Legend Bar 改造）

### 1.1 可交互轨道标签

改造 legend bar，每个轨道标签可点击选中：

```
┌─────────────────────────────────────────────────────┐
│ [■ Ch1 Acoustic Grand Piano] [■ Ch3 Violin] [+]    │
└─────────────────────────────────────────────────────┘
```

- 每个标签：`[色块] Ch{N} {乐器名}`
- 选中状态：色块边框高亮 + 背景微亮 `Color(0.15, 0.15, 0.2)`
- 高度不变（28px）
- 轨道过多时截断标签文字，`+` 按钮始终可见

### 1.2 鼠标事件

```
if y < _LEGEND_HEIGHT:
    if 点击在轨道标签范围内:
        _active_channel = 对应 channel
        queue_redraw()
    elif 点击在 "+" 按钮范围内:
        _open_gm_selector_popup()
    return  # 消费事件
```

### 1.3 新增状态

```gdscript
var _active_channel: int = 0  # 当前选中轨道
```

### 1.4 ClefStation 同步

ClefStation 在初始化时将第一个有效 channel 设为 `_active_channel`，新增轨道时同步更新 `_channel_instruments`。

## 二、GM 音色选择弹窗

### 2.1 新建 `gm_instrument_selector.gd`

`AcceptDialog` 子类，内嵌按类别分组的 `Tree`：

```
┌─ 选择音色 ──────────────────┐
│ ▸ Piano                    │
│   ▸ Acoustic Grand Piano   │
│   ▸ Bright Acoustic Piano  │
│ ▸ Strings                  │
│   ▸ Violin                 │
│   ▸ Viola                  │
│ ▸ ...                      │
└────────────────────────────┘
```

- GM 128 音色按标准 16 类分组
- 选择后返回 `{channel, preset}` 信号
- 创建新 channel：取当前最小未使用 channel（跳过 9），上限 15

### 2.2 边界情况

- channel 超过 15：弹出提示"轨道数已达上限"
- channel 9 保留给打击乐，不参与分配

## 三、音符创建（点击+拖动）

### 3.1 移除 ADD_NOTE 子模式

删除 `EditSubMode.ADD_NOTE` 及相关代码（`_temp_notes`、绘制临时音符的逻辑）。

### 3.2 拖动创建流程

**按下左键（空白区域）：**

```gdscript
_creating_note = true
_create_start_pos = mouse_pos
_create_pitch = _y_to_pitch(mouse_pos.y)
_create_start_time = _pixel_to_time(mouse_pos.x)
```

**拖动中：**

```gdscript
if _creating_note:
    _preview_note = {
        channel: _active_channel,
        pitch: _create_pitch,
        start_time: min(_create_start_time, _pixel_to_time(mouse_pos.x)),
        duration: abs(_pixel_to_time(mouse_pos.x) - _create_start_time),
        velocity: 100
    }
    queue_redraw()
```

**释放左键：**

```gdscript
if _creating_note:
    _creating_note = false
    if _preview_note.duration >= 0.05:
        push_undo(EditCommand.Type.ADD, ...)
        _notes.append(从 preview_note 构建 RollNote)
    else:
        # 单击 → 默认 1 拍音符
        push_undo(EditCommand.Type.ADD, ...)
        _notes.append(RollNote.new(_active_channel, pitch, start_time, 1拍, 100))
    _preview_note = null
    queue_redraw()
```

### 3.3 预览绘制

半透明绿色矩形 + 虚线边框，在 `_draw_notes()` 中与正式音符区分。

### 3.4 约束

- pitch：`clamp(0, 127)`
- start_time：`maxf(0, start_time)`
- 仅 EDITING 模式生效
- 允许重叠（与现有行为一致）
- 向左拖动时 start_time 取 min、duration 取 abs

## 四、复制/粘贴（Ctrl+C / Ctrl+V）

### 4.1 新增状态

```gdscript
var _clipboard: Array[RollNote] = []
var _clipboard_ref_time: float = 0.0
```

### 4.2 RollNote.duplicate()

为 `RollNote` 内部类添加 `duplicate()` 方法，深拷贝所有字段。

### 4.3 Ctrl+C

```gdscript
if event.ctrl and event.keycode == KEY_C:
    selected = _notes.filter(n => n in _selected)
    if selected.is_empty(): return
    _clipboard = selected.map(n => n.duplicate())
    _clipboard_ref_time = selected.min_by(n => n.start_time).start_time
```

### 4.4 Ctrl+V

```gdscript
if event.ctrl and event.keycode == KEY_V and !_clipboard.is_empty():
    # 三级 fallback：鼠标位置 → 播放头 → 可视区域起始
    target_time = _mouse_in_area ? x_to_time(_mouse_pos.x) : _playback_position
    if target_time < 0: target_time = _scroll_offset.x

    time_offset = target_time - _clipboard_ref_time
    new_notes = _clipboard.map(n =>
        RollNote.new(_active_channel, n.pitch, n.start_time + time_offset, n.duration, n.velocity)
    )

    push_undo(EditCommand.Type.ADD, ...)
    _notes.append_array(new_notes)
    _selected = new_notes  # 粘贴后自动选中
    queue_redraw()
```

### 4.5 设计要点

- 粘贴 channel 统一改为 `_active_channel`
- 多次 Ctrl+V 以相同偏移叠放（`_clipboard_ref_time` 固定）
- 复用 `EditCommand.Type.ADD`，Ctrl+Z 一次性撤销全部粘贴音符
- 剪贴板为空时静默忽略

## 五、文件改动范围

| 文件 | 改动 |
|------|------|
| `piano_roll.gd` | 轨道选择器交互、legend bar 绘制改造、音符创建（移除 ADD_NOTE）、复制粘贴、`RollNote.duplicate()` |
| `piano_roll_actions.gd` | 移除 ADD_NOTE 相关代码、新增轨道按钮回调 |
| `clef_station.gd` | 同步新增轨道 channel_instruments、导出时包含新增轨道 |
| 新建 `gm_instrument_selector.gd` | GM 音色分类选择弹窗 |

## 六、实现优先级

1. `RollNote.duplicate()` + 剪贴板状态 → 复制粘贴（最小改动，独立性强）
2. 音符创建（移除 ADD_NOTE，改为拖动创建）
3. Legend bar 轨道选择器交互
4. GM 音色选择弹窗 + 新增轨道
