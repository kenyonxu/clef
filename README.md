# Clef

Clef 是一个 Godot 4.6+ 的 MIDI 播放引擎插件，使用 SF2 SoundFont 合成音频，支持实时 CC / Pitch Bend / Modulation，并提供基于 Claude Code 多 Agent 协作的 LLM 辅助作曲系统。

## 特性

**MIDI 播放引擎**
- 基于 AudioStreamPlayer 池的实时 MIDI 流播放
- SF2 SoundFont 合成，支持多音色同时加载
- 实时 CC（音量/表情/声相/混响/颤音）、弯音、调制
- 可配置复音上限、循环播放、释放时间倍率
- Inspector 内预览播放，JSON ↔ MIDI 双向转换

**LLM 辅助作曲（Clef Compose）**
- 通过 `/clef-compose` 命令触发，用自然语言描述需求即可生成 MIDI
- 7 个专业 Agent 协作：旋律、和声、节奏、编配、评审、修正、调度
- ABC 记谱法 → MIDI 全自动流水线（validate → merge → convert）
- music21 技术验证（调性/音域/时值/对齐/重叠 6 项检查）
- 交互式方向小样 + Leader 驱动迭代（最多 3 轮自动优化）
- SF2 音色库感知，自动适配目标音色特性

## 快速开始

### 安装 Godot 插件

1. 将 `addons/clef/` 目录复制到你的 Godot 项目的 `addons/` 目录下
2. 在编辑器中打开 **项目 → 项目设置 → 插件**，启用 **Clef**
3. 配置默认 SoundFont：**项目 → 项目设置 → General → Clef → Default Soundfont**，选择 `.sf2` 文件

推荐使用 [GeneralUser GS](https://schristiancollins.com/generaluser.php)（~30 MB，CC BY 3.0）。

### 播放 MIDI 文件

在场景中添加 `MidiStreamPlayer` 节点，在 Inspector 中指定 MIDI 资源和 SoundFont 路径即可。

```gdscript
@onready var player: MidiStreamPlayer = $MidiStreamPlayer

func _ready():
    player.start_playback()
    player.finished.connect(_on_song_end)
```

### LLM 辅助作曲

在 Claude Code 中使用 `/clef-compose` 命令，用自然语言描述音乐需求：

```
/clef-compose 帮我写一段 boss 战斗音乐，D大调，140BPM，30秒，管弦风格
```

系统会自动完成：需求解析 → 音乐规划 → 方向小样确认 → 完整创作 → 质量评审 → 迭代优化 → 表现力注入 → MIDI 输出。

详细用法参见 [LLM 作曲使用指南](addons/clef/docs/user_docs/llm_midi_composer_guide_cn.md)。

## 编辑器工具

| 工具 | 说明 |
|------|------|
| Inspector 预览 | 选中 `MidiStreamPlayer` 节点后，Inspector 底部显示播放控制 |
| JSON → MIDI | 顶部菜单 **Clef Utility → Compose MIDI from JSON** 或右键 `.json` 文件 |
| MIDI → JSON | 顶部菜单 **Clef Utility → Export MIDI to JSON** 或右键 `.mid` / `.tres` 文件 |
| 文件导入 | `.mid` 文件自动导入为 `MidiResource`，可直接拖入场景 |

## 支持的 MIDI 事件

| 事件类型 | 说明 |
|----------|------|
| Note On/Off | 音符开/关，含力度 |
| CC 1 (Modulation) | 颤音深度 |
| CC 7 (Volume) | 通道音量 |
| CC 10 (Pan) | 声相定位 |
| CC 11 (Expression) | 表情/力度缩放 |
| CC 64 (Sustain) | 延音踏板 |
| CC 91 (Reverb) | 混响深度 |
| Pitch Bend | 弯音（±2 半音） |
| Tempo Change | 速度变化 |

## 文档

| 文档 | 说明 |
|------|------|
| [用户手册](addons/clef/docs/user_guide.md) | 插件完整使用指南（安装、播放、API、FAQ） |
| [Clef JSON v2.0 规范](addons/clef/docs/clef_json_spec.md) | JSON 格式详细规范 |
| [LLM 作曲使用指南](addons/clef/docs/user_docs/llm_midi_composer_guide_cn.md) | 自然语言描述音乐的技巧与示例 |

## 项目结构

```
addons/clef/              # Godot 插件
  player/                 # 播放引擎（MidiStreamPlayer, SF2 合成, 复音池）
  converter.gd            # JSON ↔ MidiData 转换
  midi_reader.gd          # MIDI 二进制解析
  midi_writer.gd          # MidiData → MIDI 输出
  midi_resource.gd        # Resource 子类
  editor/                 # 编辑器插件（右键菜单、Inspector）
  ui/                     # 播放器 UI
  templates/              # LLM 作曲模板
  knowledge/              # 音色库 profile
  sound_front/            # SoundFont 文件
  tests/                  # 测试

.claude/                  # Claude Code 作曲系统
  skills/clef-compose/    # 主 Skill + Python 工具链
    SKILL.md              # 作曲工作流定义
    theory.md             # 核心乐理知识
    scripts/              # abc_to_midi, validate, merge, inject, snapshot, midi-to-audio 等
    tests/                # Python 测试
  agents/                 # 7 个 Agent 定义
```

## 技术要求

- Godot 4.6+
- Python 3.10+（LLM 作曲工具链）
- music21（`pip install music21`，作曲验证）
- mido（`pip install mido`，MIDI 读写）
- FluidSynth（`midi-to-audio` 音频导出，可选）
- ffmpeg（OGG/MP3 导出，可选）
- Claude Code（LLM 作曲功能）

## 致谢

音频播放部分参考了 [arlez80/Godot-MIDI-Player](https://github.com/arlez80/Godot-MIDI-Player) 的实现思路，包括 mix latency 补偿、ADSR 包络插值方式和 release delay 机制。

## 许可证

MIT
