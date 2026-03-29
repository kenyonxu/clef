# Clef — MIDI Playback Engine for Godot

Clef 是一个 Godot 4.6+ 的 MIDI 播放引擎插件，使用 SF2 SoundFont 合成音频，支持实时 CC / Pitch Bend / Modulation，并提供 LLM 辅助编曲工具链。

## 特性

- **SF2 合成** — 基于 AudioStreamPlayer 池架构，使用 SoundFont 2 文件合成音频
- **完整 MIDI 支持** — Note On/Off、Program Change、Control Change、Pitch Bend、Tempo Change
- **立体声采样** — 自动检测 SF2 立体声采样对，生成交错立体声 AudioStreamWAV
- **实时控制** — CC1 调制、CC7 音量、CC10 声相、CC11 表情、CC64 延音踏板、RPN 弯音灵敏度
- **多声道混音** — 自动创建 16 通道音频总线 + 独立声相
- **语音池** — 可配置复音数（默认 32），按通道窃取策略
- **LLM 编曲** — Clef JSON v1.1 格式 + LLM 系统提示词，支持 AI 辅助作曲
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
| `max_polyphony` | `int` | `32` | 最大同时发声数（1-128） |
| `bus` | `String` | `"Master"` | 输出音频总线 |

## 信号

| 信号 | 参数 | 说明 |
|------|------|------|
| `note_triggered` | `channel, pitch, velocity` | 每次触发音符时发出 |
| `finished` | — | 非循环模式下播放结束时发出 |

## 编辑器工具

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

Clef 定义了 **Clef JSON v1.1** 格式，可将 MIDI 数据序列化为人类可读的 JSON。配合 LLM（ChatGPT / Claude 等）可实现 AI 辅助作曲。

- 系统提示词：[celf_composer_llm_system_prompt_cn.md](docs/user_docs/celf_composer_llm_system_prompt_cn.md)
- 格式规范：[clef_json_spec.md](docs/clef_json_spec.md)
- 基础模板：[templates/default.json](templates/default.json)
- 完整示例：[templates/example_full.json](templates/example_full.json)

LLM 支持三种工作模式：
1. **创作** — 根据自然语言描述生成 Clef JSON
2. **分析** — 解读提供的 Clef JSON 的风格、配器、结构
3. **参考编曲** — 参考已有 JSON 结合新需求创作

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
