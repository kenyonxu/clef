# Clef Station — Godot 编辑器音频工作台

> 日期：2026-03-29
> 状态：已确认，待实现

## 概述

Clef Station 是 Clef MIDI 插件的编辑器主界面，与 Godot 的 2D/3D/Script 同级。为游戏音频开发提供音色浏览、混音调试、MIDI 监视等开发调试工具。

## 目标用户

游戏音频开发者在 Godot 编辑器中调试 MIDI 播放、调整音色、检查混音效果。

## 功能分层

### 核心层（Phase 2-3）

1. **音色浏览器** — SF2 Patch 列表、分组显示、搜索过滤、点击试听、Patch 详细信息
2. **MIDI 监视器** — 实时事件流（NoteOn/Off、CC、PitchBend）、颜色编码、通道过滤、统计栏

### 扩展层（Phase 4）

3. **迷你混音台** — 通道音量推子、Mute/Solo、播放控制、小节/拍号显示
4. **波形可视化** — 可折叠的实时音频波形显示

### 打磨层（Phase 5）

5. 键盘快捷键、布局持久化、暗色主题适配

## 界面布局

三栏布局，左栏和右栏可折叠：

```
┌─────────────────────────────────────────────────────┐
│  2D │ 3D │ Script │ Audio │                         │
├──────────┬──────────────────────┬───────────────────┤
│ 音色浏览器 │     主工作区         │   MIDI 监视器      │
│          │                      │                   │
│ [Patch列表]│  ┌─迷你混音台──────┐ │  [音符实时滚动]    │
│ [试听按钮]│  │ CH1 ████░░ M S  │ │  CC1: 64          │
│ [搜索过滤]│  │ CH2 █████░ M S  │ │  CC7: 87          │
│          │  │ CH3 ███░░░ M S  │ │  Pitch: +200      │
│ [SF2信息] │  │ CH4 ██████ M S  │ │  Bar: 12/32       │
│          │  │ Drum █████░ M S  │ │  Beat: 3/4        │
│          │  └──────────────────┘ │  BPM: 120         │
│          │                      │                   │
│          │  [▶ 播放] [⏹ 停止]    │                   │
├──────────┴──────────────────────┴───────────────────┤
│  波形/频谱可视化（可折叠）                              │
└─────────────────────────────────────────────────────┘
```

## 组件详细设计

### 1. 音色浏览器（左栏）

- 按 GM 标准分类分组（Piano、Strings、Brass 等）
- Tree 控件显示 Patch 列表，支持展开/折叠
- 每项右侧有试听按钮 `[▶]`，播放该 Patch 的 C4 音符
- 顶部搜索框，支持按名称或编号过滤
- 底部信息面板：选中 Patch 的音域、采样数、Sweet Spot
- 数据来源：`sf2_profiler.py` 生成的 profile JSON

### 2. 迷你混音台 + 播放控制（中栏）

- 每通道一行：名称、音量推子（HSlider）、音量值（dB）、Mute/Solo 按钮
- Master 通道推子
- 播放控制栏：播放/停止/跳转按钮 + 进度条 + BPM + 拍号显示
- 当前位置：小节号/总小节数 + 当前拍
- 可折叠波形可视化区域

### 3. MIDI 监视器（右栏）

- 实时事件列表，按时间倒序滚动
- 颜色编码：Note=蓝、CC=绿、PitchBend=橙、Program Change=紫
- 顶部工具栏：清除、自动滚动开关、过滤器下拉（全部/按通道/按类型）
- 底部统计栏：活跃音符数、事件速率
- 鼓组音符自动映射为名称（Kick、Snare、HiHat 等）

## 技术决策

| 决策 | 方案 | 理由 |
|------|------|------|
| 主屏幕实现 | `EditorPlugin.make_main_screen()` | Godot 4 原生支持，与 2D/3D 同级 |
| 信号扩展 | MidiStreamPlayer 添加 note_on/off/cc/pitchbend 信号 | 最小侵入，不改变播放逻辑 |
| 音量控制 | 直连 `channel_state.volume_db` | 复用现有通道状态系统 |
| Solo 逻辑 | 启用 Solo 时只播放 Solo 通道，其余静音 | 标准混音台行为 |
| 波形数据 | `AudioServer.get_bus_peak_volume_left/right()` | Godot 内置 API，无额外依赖 |
| 面板布局 | HSplitContainer 嵌套 | Godot 原生可拖拽分割 |
| 试听实现 | 通过 ClefBank 创建临时 ClefVoice 播放单音 | 复用现有音色引擎 |
| Patch 数据 | 读取 sf2_profiler.py 输出的 JSON | 已有工具，无需重新实现 |

## 文件结构

```
addons/clef/editor/
  clef_station_plugin.gd      # EditorPlugin 主入口
  clef_station.gd             # 主界面 Control（三栏布局）
  soundfont_browser/
    soundfont_browser.gd      # 音色浏览器面板
    patch_list.gd             # Patch 列表控件
    patch_info_panel.gd       # Patch 信息面板
  midi_monitor/
    midi_monitor.gd           # MIDI 监视器面板
    midi_event_item.gd        # 事件行控件
  mixer/
    clef_mixer.gd             # 混音台面板
    channel_strip.gd          # 单通道推子
    transport_bar.gd          # 播放控制栏
  visualizer/
    waveform_display.gd       # 波形绘制控件
```

## 实现阶段

### Phase 1 — 基础框架

- EditorPlugin 主屏幕注册（Clef Station 标签出现在顶部）
- 三栏 HSplitContainer/VSplitContainer 骨架
- MidiStreamPlayer 信号扩展（note_on_emitted、note_off_emitted、cc_emitted、pitch_bend_emitted）

### Phase 2 — 音色浏览器

- SF2 profile JSON 加载与解析
- Patch 列表 Tree 控件（分组 + 搜索过滤）
- 试听功能（通过 ClefBank 播放单音）
- Patch 信息面板（音域、采样数、Sweet Spot）

### Phase 3 — MIDI 监视器

- 连接 MidiStreamPlayer 信号
- 实时事件列表（Tree 或 ItemList，颜色编码）
- 自动滚动 + 手动滚动切换
- 通道/类型过滤
- 统计栏（活跃音符数、事件速率）

### Phase 4 — 迷你混音台

- 通道音量推子（HSlider）+ Mute/Solo 按钮
- Master 推子
- 播放控制（播放/停止/跳转）
- 位置进度条 + 小节/拍号显示
- 波形可视化（可折叠，使用 AudioServer 数据）

### Phase 5 — 打磨

- 键盘快捷键（空格=播放/暂停、M=静音等）
- 布局持久化（保存分割位置和面板状态）
- 暗色主题适配
- 性能优化（大量事件时的列表虚拟化）
