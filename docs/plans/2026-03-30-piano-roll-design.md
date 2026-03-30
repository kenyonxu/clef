# Piano Roll 播放可视化设计

## 概述

为 Clef Station 中栏新增实时钢琴卷帘面板，在播放 MIDI 时可视化音符分布。核心用途是辅助 `/clef-compose` 工作流中审查生成音乐的质量。

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 面板位置 | 中栏中部（Transport 和 Mixer 之间） | 需要垂直空间，不挤占其他面板 |
| 通道显示 | 所有通道叠加，颜色区分 | 直观看到声部间关系 |
| 交互 | 可点击跳转播放位置 | "听到问题 → 点击定位" 的自然工作流 |
| 实现方式 | Control._draw() 自定义绘制 | 轻量简洁，500 矩形对 GPU 无压力 |

## 组件与布局

新增 `PianoRoll` 组件（继承 `Control`），位于 `addons/clef/editor/piano_roll/piano_roll.gd`。

中栏布局（center_vbox）：
```
Load MIDI | Auto              ← 加载按钮行
Play | Pause | Stop | Loop | ████████░░░ 00:30/02:15  ← TransportBar
┌─────────────────────────────┐
│ C6 ┤                       │
│ B5 ┤  ████                 │  ← PianoRoll（新增）
│ A5 ┤      ████             │
│ G5 ┤                       │
│ ...│  ▼ 播放线              │
│ C3 ┤ ████                  │
│    └───────────────────────┘
Ch1 [====] M  Ch2 [====]     ← MiniMixer
```

- 默认高度 160px，`custom_minimum_size = Vector2i(0, 160)`
- `SIZE_EXPAND_FILL` 填充剩余空间
- 显示音域：当前 MIDI 文件实际使用的 min/max pitch，两侧各留 1 个八度余量

## 绘制细节

### 坐标映射

- 横轴：时间（秒）→ 像素。初始 pixels_per_second 让整首曲子铺满可视宽度
- 纵轴：音高（0-127）→ 像素。初始 pixels_per_note ≈ 4px（紧凑可区分）

### 音符块

- 填充矩形，颜色由通道决定（与 MIDI Monitor 共用调色板）
- 宽度 = duration × pixels_per_second
- 高度 = pixels_per_note - 1（1px 间隙）
- 力度映射亮度：`color * (0.5 + velocity/127 * 0.5)`

### 播放线

- 竖直白色细线（2px），跟随播放位置
- `_process()` 每帧更新，调用 `queue_redraw()`

### 背景网格

- 水平线：每个 C 音画一条稍亮线（区分八度）
- 不画垂直线（避免噪音）

## 交互与数据流

### 点击跳转

- 监听 `gui_input`，左键点击计算时间位置
- 通过 `seek_requested(position)` 信号通知 TransportBar 和 EditorPlayer

### 数据来源

- 加载 MIDI 时从 MidiData 提取 Note On/Off 对
- 缓存为 `Array[PianoRollNote]`（`{channel, pitch, start_time, duration, velocity}`）
- 不每帧重新解析

### 连接

```
EditorPlayer.load_file(path)
    → 解析 MidiData
    → 提取音符列表
    → PianoRoll.set_notes(note_array, duration)
    → PianoRoll.queue_redraw()

EditorPlayer._process()
    → 更新 position
    → PianoRoll.set_playback_position(position)
    → queue_redraw()

PianoRoll.gui_input()
    → 计算 seek 位置
    → emit seek_requested(position)
    → TransportBar 收到后转发给 EditorPlayer
```

### 性能策略

- `queue_redraw()` 仅播放时每帧调用，不播放时零开销
- `_draw()` 直接遍历数组绘制，无子节点管理

## 文件结构

```
addons/clef/editor/piano_roll/
    piano_roll.gd          # PianoRoll Control，绘制与交互
```
