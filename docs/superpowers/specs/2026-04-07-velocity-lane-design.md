# Velocity Lane 设计规格

**日期**: 2026-04-07
**项目**: clef-dev (Clef MIDI Plugin)
**范围**: Piano Roll 的 velocity 可视化编辑

## 背景

当前 Piano Roll 的 velocity 编辑仅通过右键菜单 → "Edit velocity..." 弹出对话框，统一设置选中音符的 velocity 值。无法直观看到各音符的力度差异，也无法快速做出力度起伏。

## 设计目标

- 提供直观的 velocity 可视化，一眼看出力度趋势
- 支持逐音符拖拽调整 velocity
- 与现有 Piano Roll 的滚动/缩放/选中状态同步
- 作为独立可折叠面板，不干扰现有音符编辑

## 架构

### 组件结构

```
ClefStation (VBoxContainer)
├── PianoRoll (Control)
├── VelocityToggleButton (Button) — 折叠/展开
└── VelocityLane (Control) — 新增
    ├── VSlider[] — 每个音符一个
    └── 刻度标签 (127 / 64 / 0)
```

`VelocityLane` 是独立的 `Control` 子类（`velocity_lane.gd`），放在 `ClefStation` 的 VBox 中，位于 `PianoRoll` 下方。

### 信号同步

**PianoRoll → VelocityLane:**

| 信号 | 用途 |
|------|------|
| `view_offset_changed(view_offset, zoom_level, pps, duration)` | 同步水平滚动和缩放，保持音符与 slider 对齐 |
| `selection_changed(indices[])` | 高亮被选中音符对应的 slider |
| `track_changed(channel, preset)` | 切换活动通道，过滤显示的音符 |
| `note_edited()` | 音符被修改（拖拽/删除/添加），刷新 slider 列表 |

**VelocityLane → PianoRoll:**

| 信号 | 用途 |
|------|------|
| `velocity_changed(note_index: int, new_velocity: int)` | 更新 RollNote.velocity，触发 undo 快照 |

PianoRoll 需要新增 `selection_changed` 信号（当前 selection 变化未发射信号）。

### 数据传递

VelocityLane 通过 `set_notes(notes: Array[RollNote])` 方法从 PianoRoll 获取音符数据引用。每次 `note_edited()` 触发时 PianoRoll 调用此方法刷新。`velocity_changed` 信号中的 `note_index` 是 `_notes[]` 数组的原始索引（非过滤后的局部索引）。

## VelocityLane 控件详情

### 文件

- `addons/clef/editor/piano_roll/velocity_lane.gd` (class_name VelocityLane, extends Control)

### 过滤逻辑

只显示 `_active_channel` 对应的音符。通道切换通过 `track_changed` 信号获知。

### VSlider 配置

- `min_value`: 1
- `max_value`: 127
- `step`: 1
- `vertical`: true
- 宽度: 与对应音符的像素宽度一致（`duration * pps`）
- 位置: 与对应音符的水平起始位置一致（`_time_to_x(start_time)`）
- 颜色: 使用与 Piano Roll 相同的 `ChannelColors.COLORS[channel % 16]`，选中时加白色边框

### 滚动/缩放同步

VelocityLane 接收 `view_offset_changed(view_offset, zoom_level, pps, duration)` 后：
- 使用 `pps`（pixels per second）计算每个音符的像素位置和宽度
- 使用 `view_offset` 计算水平偏移
- 超出可见区域的 slider 设置 `visible = false`
- scroll/zoom 时重建或重新定位 slider（每次 view 变化时调用 `_rebuild_sliders()`）

### Undo/Redo

VelocityLane 不直接操作 `_notes` 数组。通过 `velocity_changed` 信号通知 PianoRoll，由 PianoRoll 的 `begin_command / commit_command` 机制处理 undo 快照。快照格式复用现有的 `velocity_changes` 结构。

### 性能

- 编辑模式下音符数量通常在数十到数百个，VSlider 控件数量可控
- `_rebuild_sliders()` 在 scroll/zoom 时调用，使用 `queue_deferred()` 避免频繁重建
- 不可见的 slider 设置 `visible = false`，不参与渲染

## 折叠/展开

- 在 VelocityLane 上方放置一个 Button（"▼ Velocity" / "▶ Velocity"）
- 点击切换 VelocityLane 的 `visible` 属性
- 记住用户上次的状态偏好（可选，非首期范围）

## 与现有功能的关系

- 保留右键菜单 "Edit velocity..." 作为替代入口（适用于精确数值输入场景）
- 保留音符亮度随 velocity 变化的视觉效果
- velocity 对音量和音色的影响（ClefVoice / Sf2Bank）不变

## 不在范围内

- 批量渐变工具（渐强/渐弱曲线）
- 刷选模式（画笔式批量编辑）
- velocity automation 曲线
- 多通道混显
