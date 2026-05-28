# Clef — MIDI Playback Engine for Godot

Clef 是一个 Godot 4.6+ 的 MIDI 播放引擎插件，使用 SF2 SoundFont 合成音频，支持实时 CC / Pitch Bend / Modulation，并提供 LLM 辅助编曲工具链。

## 特性

- **SF2 合成** — 基于 AudioStreamPlayer 池架构，使用 SoundFont 2 文件合成音频
- **SF2 滤波** — 离线 biquad LPF 预处理 SF2 采样，还原 SoundFont 原始音色
- **完整 MIDI 支持** — Note On/Off、Program Change、Control Change、Pitch Bend、Tempo Change
- **立体声采样** — 自动检测 SF2 立体声采样对，生成交错立体声 AudioStreamWAV
- **实时控制** — CC1 调制、CC7 音量、CC10 声相、CC11 表情、CC64 延音踏板、RPN 弯音灵敏度
- **多声道混音** — 自动创建 16 通道音频总线 + 独立声相
- **总线效果器** — ClefMaster 总线集成 Compressor（动态压缩）和 6 段 EQ（均衡）
- **语音池** — 可配置复音数（默认 64），按通道窃取策略
- **LLM 编曲** — Clef JSON v1.1 格式 + LLM 系统提示词，支持 AI 辅助作曲
- **Clef Station** — 编辑器内 MIDI 工作站面板，集成音色浏览、播放控制、混音台和 MIDI 监视器
- **编辑器工具** — Inspector 预览播放、JSON↔MIDI 互转、文件系统右键菜单

## 安装

1. 将 `addons/clef/` 目录复制到项目的 `addons/` 目录下
2. 在 Godot 编辑器中，打开 **项目 → 项目设置 → 插件**，启用 **Clef**
3. 配置默认 SoundFont：**项目 → 项目设置 → General → Clef → Default Soundfont**，选择 `.sf2` 文件

### 推荐的免费 SoundFont

| SoundFont | 许可证 | 大小 | 说明 |
|-----------|--------|------|------|
| [GeneralUser GS](https://schristiancollins.com/generaluser.php) | CC BY 3.0 | ~30 MB | 完整 GM/GS 音色集，质量高，体积小 |
| [FluidR3 GM](https://musical-artifacts.com/artifacts/738) | 自由分发 | ~142 MB | MuseScore 默认音色，音质优秀 |
| [FreePats GM](https://freepats.zenvoid.org/SoundSets/general-midi.html) | CC0 | ~227 MB | 公共领域，无需署名，GM 覆盖仍在完善中 |

> 游戏开发推荐 **GeneralUser GS**（体积小、质量高，CC BY 3.0 仅需在 credits 中署名）。更多选择参见 [awesome-soundfonts](https://github.com/ad-si/awesome-soundfonts)。

## 快速开始

### 播放 MIDI 文件

1. 将 `.mid` 文件放入项目资源目录，Godot 会自动导入为 `MidiResource`
2. 创建 `Node`，附加 `MidiStreamPlayer` 脚本
3. 在 Inspector 中设置 `Midi Resource` 和 `Soundfont` 属性
4. 运行场景即可播放

### 通过代码控制

```gdscript
var player := MidiStreamPlayer.new()
player.midi_resource = preload("res://music/my_song.tres")
player.soundfont = "res://soundfonts/my_piano.sf2"
player.loop = true
player.volume_db = -10.0
add_child(player)
player.start_playback()
```

### 暂停 / 恢复 / 跳转

```gdscript
player.pause()
player.resume()
player.seek(5.0)  # 跳转到第 5 秒
var position: float = player.get_playback_position()
```

## MidiStreamPlayer 属性

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `midi_resource` | `MidiResource` | `null` | 要播放的 MIDI 资源 |
| `soundfont` | `String` | `""` | SF2 文件路径 |
| `loop` | `bool` | `false` | 是否循环播放 |
| `release_multiplier` | `float` | `1.0` | 释放时长倍率（0.1-2.0） |
| `autoplay` | `bool` | `false` | 场景加载后自动播放 |
| `volume_db` | `float` | `-20.0` | 主音量（dB） |
| `pitch_scale` | `float` | `1.0` | 全局音高缩放 |
| `max_polyphony` | `int` | `64` | 最大同时发声数（1-128） |
| `bus` | `String` | `"Master"` | 输出音频总线 |
| `reverb_enabled` | `bool` | `true` | 启用混响效果 |
| `reverb_room_size` | `float` | `0.29` | 混响房间大小（0-1） |
| `reverb_wet` | `float` | `0.15` | 混响湿信号比例（0-1） |
| `chorus_enabled` | `bool` | `true` | 启用合唱效果 |
| `chorus_wet` | `float` | `0.2` | 合唱湿信号比例（0-1） |
| `compressor_enabled` | `bool` | `false` | 启用动态压缩（多声部叠加时防止削波） |
| `compressor_threshold_db` | `float` | `-12.0` | 压缩阈值（-60~0 dB） |
| `compressor_ratio` | `float` | `4.0` | 压缩比（1~64） |
| `compressor_gain_db` | `float` | `0.0` | 压缩补偿增益（-20~20 dB） |
| `eq_enabled` | `bool` | `false` | 启用 6 段均衡器（在 Audio 面板调参） |

## 信号

| 信号 | 参数 | 说明 |
|------|------|------|
| `note_triggered` | `channel, pitch, velocity` | 每次触发音符时发出 |
| `finished` | — | 非循环模式下播放结束时发出 |

## 编辑器工具

### Clef Station — MIDI 工作站面板

启用插件后，编辑器底部会出现 **Clef Station** 面板，提供 MIDI 播放、音色浏览、混音控制和实时事件监视功能。面板采用三栏可拖拽布局，所有分割位置和面板可见性会自动保存。

#### 左栏：Soundfont 浏览器

浏览当前加载的 SF2 音色库，按分类（钢琴、弦乐、铜管等）和乐器名称搜索音色。选中音色可直接试听。

- 搜索框支持模糊匹配乐器名
- 分类折叠/展开
- 点击音色条目播放试听

#### 中栏：播放控制 + 钢琴卷帘 + 混音台

从上到下依次为传输控制栏、钢琴卷帘和迷你混音台。

**传输控制栏：**
- **Load MIDI** — 加载 `.mid` / `.tres` / `.json` 文件，也支持从文件系统拖拽到面板
- **Auto** — 开启后每次打开编辑器自动加载上次播放的文件
- **Play / Pause / Stop** — 播放控制
- **Loop** — 循环播放
- **进度条** — 显示当前播放位置，可点击跳转

**钢琴卷帘（Piano Roll）：**
- 实时显示所有 MIDI 通道的音符分布，横轴时间、纵轴音高
- 不同通道以颜色区分，力度映射为亮度
- 播放时白色竖线跟随播放位置移动
- 点击卷帘任意位置可跳转播放
- 完整编辑功能：选中、移动、删除音符，框选批量操作，复制粘贴，撤销重做，力度编辑

**迷你混音台：**
- 16 通道独立音量滑块 + 静音按钮
- 每个通道显示当前 GM 乐器名称（Program Change 后自动更新）
- Master 主音量控制
- 声相和乐器名称以 tooltip 形式显示

#### 右栏：MIDI 监视器

实时显示 MIDI 事件流，支持按类型过滤和自动滚动。

**事件类型及颜色：**
- **NoteOn**（绿色）— 音符触发，显示通道、音高、力度
- **NoteOff**（灰色）— 音符释放，显示通道和音高
- **CC**（蓝色）— 控制变更，显示控制器编号和值
- **PB**（橙色）— 弯音轮
- **PC**（紫色）— 音色切换

**工具栏功能：**
- **Ch** — 通道过滤（默认 All）
- **NoteOn / CC / PB / PC** — 按类型切换过滤
- **Auto** — 自动滚动到最新事件
- **Clear** — 清空事件日志
- **Copy** — 复制当前可见事件到剪贴板

**底部状态栏** — 显示总事件数、当前活跃音符数和每秒事件率。

### Inspector 预览

选中 `MidiResource` 文件，Inspector 底部会显示 ▶ Play / ⏹ Stop 按钮和进度条，可直接在编辑器中试听。

### JSON ↔ MIDI 转换

**方法一：顶部菜单**
- **项目 → Clef Utility → Compose MIDI from JSON...** — 选中 `.json` 文件后，转换为 `.mid`
- **项目 → Clef Utility → Export MIDI to JSON...** — 选中 `.mid` / `.tres` 文件后，导出为 `.json`

**方法二：文件系统右键菜单**
- 右键 `.json`（Clef 格式）→ **Convert to MIDI**
- 右键 `.mid` / `.tres` → **Export to JSON**

### Inspector 导出

选中 `MidiResource` 文件，Inspector 底部的 **Export JSON** 按钮可直接导出为 `.json`。

## LLM 辅助编曲

Clef 定义了 **Clef JSON v2.0** 格式，可将 MIDI 数据序列化为人类可读的 JSON。配合 LLM 可实现 AI 辅助作曲。

- [用户手册 (中文)](docs/user_guide_cn.md) / [User Manual (English)](docs/user_guide_en.md)
- [LLM 作曲指南 (中文)](docs/user_docs/llm_midi_composer_guide_cn.md) / [LLM Composition Guide (English)](docs/user_docs/llm_midi_composer_guide_en.md)

> Clef 还提供了基于 Claude Code 的 7-Agent 全自动作曲系统，详见 [项目主页](../../README.md)。

## 支持的 MIDI 事件

| 事件 | CC/类型 | 说明 |
|------|---------|------|
| Note On/Off | — | 音符触发与释放 |
| Program Change | — | 乐器切换（GM 音色号 0-127） |
| Control Change 1 | Modulation | 颤音深度 |
| Control Change 6/38 | RPN Data Entry | 弯音灵敏度配置 |
| Control Change 7 | Volume | 通道音量 |
| Control Change 10 | Pan | 声相 |
| Control Change 11 | Expression | 表情/力度缩放 |
| Control Change 64 | Sustain Pedal | 延音踏板 |
| Control Change 100/101 | RPN LSB/MSB | RPN 参数选择 |
| Control Change 120 | All Sound Off | 立即静音 |
| Control Change 123 | All Notes Off | 释放所有音符 |
| Pitch Bend | — | 弯音（14-bit，±2 半音） |
| Tempo Change | Meta | 速度变化 |

## 致谢

本项目音频播放部分参考了 [arlez80/Godot-MIDI-Player](https://github.com/arlez80/Godot-MIDI-Player) 的实现思路，包括 mix latency 补偿、ADSR 包络插值方式和 release delay 机制。

## 许可证

MIT License
