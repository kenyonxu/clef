# Clef 用户手册

## 目录

1. [安装与配置](#1-安装与配置)
2. [播放 MIDI 文件](#2-播放-midi-文件)
3. [Inspector 预览](#3-inspector-预览)
4. [Clef Station 工作站面板](#4-clef-station-工作站面板)
5. [JSON ↔ MIDI 转换](#5-json--midi-转换)
6. [MidiStreamPlayer 属性参考](#6-midistreamplayer-属性参考)
7. [脚本 API](#7-脚本-api)
8. [LLM 辅助编曲](#8-llm-辅助编曲)
9. [Python 工具链](#9-python-工具链)
10. [常见问题](#10-常见问题)

---

## 1. 安装与配置

### 安装插件

1. 将 `addons/clef/` 目录复制到项目的 `addons/` 下
2. 打开 Godot 编辑器 → **项目 → 项目设置 → 插件**
3. 找到 **Clef**，点击 **启用**

### 配置默认 SoundFont

1. 打开 **项目 → 项目设置 → General**
2. 找到 **Clef → Default Soundfont**
3. 选择一个 `.sf2` 文件

配置后，`MidiStreamPlayer` 节点会自动使用该 SoundFont（除非手动指定了其他文件）。

---

## 2. 播放 MIDI 文件

### 方式一：场景节点

1. 将 `.mid` 文件拖入项目资源目录（Godot 会自动导入为 `MidiResource`）
2. 在场景中创建一个 `Node`
3. 附加 `MidiStreamPlayer` 脚本
4. 在 Inspector 中：
   - **Midi Resource**：拖入导入的 `.tres` 文件
   - **Soundfont**：选择 `.sf2` 文件（留空则使用默认配置）
5. 运行场景

### 方式二：代码创建

```gdscript
var player := MidiStreamPlayer.new()
player.midi_resource = preload("res://music/song.tres")
player.soundfont = "res://soundfonts/piano.sf2"
player.loop = true
add_child(player)
player.start_playback()
```

### 播放控制

| 方法 | 说明 |
|------|------|
| `start_playback(from_position)` | 开始播放，可选起始位置（秒） |
| `stop()` | 停止并重置到开头 |
| `pause()` | 暂停 |
| `resume()` | 恢复播放 |
| `seek(position)` | 跳转到指定位置（秒） |
| `get_playback_position()` | 获取当前播放位置（秒） |
| `is_playing()` | 是否正在播放 |

---

## 3. Inspector 预览

在编辑器中可以直接试听 MIDI 资源，无需运行场景。

1. 在文件系统面板中选中一个 `MidiResource`（`.tres`）文件
2. Inspector 底部会出现 Clef 预览面板：
   - **▶ Play** — 开始播放
   - **⏸ Pause** — 暂停 / 恢复
   - **⏹ Stop** — 停止播放
   - 进度条 — 拖拽可跳转播放位置
   - 时间标签 — 显示当前时间 / 总时长
   - **Export JSON** — 导出为 Clef JSON v2.0 格式（供 LLM 编曲使用）

> 前提：已在项目设置中配置了默认 SoundFont。未配置时播放按钮不可用，并显示提示文字。

---

## 4. Clef Station 工作站面板

Clef Station 是集成在编辑器底部的 MIDI 工作站面板，提供音色浏览、播放控制、混音调节和实时 MIDI 事件监视功能。启用 Clef 插件后自动出现。

### 面板布局

面板采用三栏可拖拽分割布局，分割位置和面板可见性会自动保存到配置文件，下次打开编辑器时恢复。

| 栏 | 内容 | 可通过工具栏隐藏 |
|----|------|-----------------|
| 左栏 | Soundfont 浏览器 | 是（**SF2 Browser** 按钮） |
| 中栏 | 播放控制 + 迷你混音台 | 始终显示 |
| 右栏 | MIDI 监视器 | 是（**MIDI Monitor** 按钮） |

拖拽栏间的分割线可调整宽度。

### 4.1 加载和播放 MIDI

#### 加载文件

支持三种文件格式：`.mid`、`.tres`（MidiResource）、`.json`（Clef JSON）。

1. 点击 **Load MIDI** 按钮，在弹出的对话框中选择文件
2. 或者直接从文件系统面板拖拽文件到 Clef Station 面板

#### 自动加载

开启 **Auto** 按钮后，每次打开编辑器会自动加载上次播放的文件。

#### 播放控制

| 控件 | 说明 |
|------|------|
| **Play** | 开始播放 |
| **Pause** | 暂停 / 恢复 |
| **Stop** | 停止播放并回到开头 |
| **Loop** | 循环播放（开启后播放结束自动重新开始） |
| 进度条 | 显示当前位置 / 总时长，点击可跳转 |

> 播放使用编辑器音频总线，不需要运行游戏场景即可试听。

### 4.2 钢琴卷帘

钢琴卷帘位于传输控制栏和混音台之间，实时显示 MIDI 音符在时间轴上的分布，并支持编辑和审听反馈。

**显示内容：**
- 横轴为时间（秒），纵轴为音高（MIDI 0-127）
- 所有通道的音符叠加显示，不同通道以颜色区分
- 音符力度映射为亮度：力度越高颜色越亮
- 背景网格中每个 C 音有较亮的分隔线，便于识别八度

**播放时的表现：**
- 白色竖线跟随播放位置实时移动
- 停止时播放线回到开头

> 音域范围根据当前 MIDI 文件自动计算，两侧各留一个八度余量。

#### 4.2.1 图例栏

卷帘顶部图例栏显示当前轨道信息，并提供快速操作按钮：

| 区域 | 说明 |
|------|------|
| 轨道列表 | 左侧显示各轨道的通道号和乐器名称，点击可切换当前编辑轨道 |
| **+** 按钮 | 添加新轨道（仅编辑模式可用，非活跃模式置灰） |
| **⩩** 按钮 | 导出 Agent 反馈 JSON（仅反馈模式可用，非活跃模式置灰） |
| **⤓** 按钮 | 导出编辑后的 MIDI 文件（仅编辑模式可用，非活跃模式置灰） |

右键点击轨道名称可弹出 **切换音色** 菜单，打开 GM 音色选择器（128 种标准音色，按类别分组）。若已加载 SF2 音色库，优先显示实际可用音色；未加载时 fallback 为 GM 硬编码列表。

#### 4.2.2 三态模式系统

钢琴卷帘提供三种互斥的工作模式，通过模式栏按钮切换（当前模式以蓝色边框高亮）：

| 模式 | 按钮 | 说明 |
|------|------|------|
| **播放模式** | ▶ 播放模式 | 只读浏览，点击跳转播放位置 |
| **编辑模式** | ✏ 编辑模式 | 完整编辑：移动、调整、删除音符 |
| **反馈模式** | ❗ 反馈模式 | 审听标注：选中、屏蔽、标注问题音符 |

模式栏和传输控制栏（Play/Stop/Pause）独立运作——在任何模式下都可以通过传输栏播放/暂停 MIDI。

##### 播放模式

默认模式，适合浏览和试听 MIDI 文件。

- 点击卷帘任意位置跳转到对应时间点
- 使用传输栏控制播放/暂停/停止
- 不可选中或编辑音符

##### 编辑模式

完整的音符编辑功能，适合微调和修改 MIDI 内容。

- **创建音符**：在空白处拖拽水平方向创建新音符，松开鼠标完成
- **选中**：单击音符选中，Ctrl+点击追加/取消选中
- **框选**：在空白处拖拽拉框批量选中
- **移动**：拖拽选中的音符水平/垂直移动
- **调整时长**：拖拽音符左/右边缘
- **删除**：选中后按 Delete 键，或右键 → 删除音符
- **复制/粘贴**：Ctrl+C 复制选中音符，Ctrl+V 粘贴到当前播放位置
- **音高调整**：右键 → 音高 +1 / 音高 -1
- **力度编辑**：右键 → 编辑力度...，在弹窗中设置 0-127 的值
- **屏蔽**：右键 → 屏蔽选中音符 / 反向屏蔽
- **撤销/重做**：Ctrl+Z / Ctrl+Shift+Z
- **导出 MIDI**：点击图例栏 **⤓** 按钮或右键 → 导出修改后的 MIDI，弹出 FileDialog 确认路径
- **导出 ABC**：右键 → 导出修改后的 ABC
- **缩放**：Ctrl+= 放大，Ctrl+- 缩小
- **平移**：中键拖拽平移视图
- 编辑修改实时同步到播放器（无需保存即可试听效果）

> 编辑时播放游标隐藏。修改仅在内存中生效，不影响原始 MIDI 文件，除非手动导出。复制粘贴和批量操作均支持撤销。

##### 反馈模式

专注审听和标注问题音符，适合 LLM 作曲后的质量审查。

- **选中**：单击/框选/Ctrl+点击（与编辑模式相同）
- **添加标注**：右键 → 添加标注...，选择严重度（info/warning/error）并填写备注
- **屏蔽**：右键 → 屏蔽选中音符 / 反向屏蔽
- **生成反馈**：点击图例栏 **⩩** 按钮或右键 → 生成 Agent 反馈，弹出 FileDialog 确认路径，导出结构化 JSON 供 LLM 迭代改进
- **播放**：传输栏正常工作，可边听边标注
- 标注仅在反馈模式下可见（彩色三角形标记在音符上方）

> 反向屏蔽会屏蔽所有未选中的音符，方便单独试听某个片段。

##### Agent 反馈 JSON 格式（v2）

反馈 JSON 包含两部分信息：

```json
{
  "version": 2,
  "selection": {
    "count": 5,
    "pitches": [60, 62, 64, 67, 72],
    "channels": [0],
    "time_range": {"start": 1.5, "end": 4.0}
  },
  "annotations": [
    {"note_index": 2, "pitch": 64, "severity": "error", "note": "avoid leap"}
  ]
}
```

- **selection** — 当前选区的上下文信息（音符数量、音高集合、通道、时间范围），帮助 Agent 区分单选与多选意图
- **annotations** — 用户标注列表，每个标注关联到具体音符索引

### 4.3 迷你混音台

混音台显示 16 个 MIDI 通道的音量控制和一个 Master 主音量。

#### 通道控制

每个通道包含：

- **Ch 标签** — 通道编号（Ch 1 - Ch 16）
- **乐器名称** — 当前 GM 音色名（Program Change 后自动更新，如 "Acoustic Grand Piano"）
- **音量滑块** — 拖拽调节通道音量（范围 -80 dB ~ +6 dB）
- **静音按钮** — 点击静音/取消静音

#### Master 控制

- **Master** 标签 + 音量滑块 — 控制整体输出音量

#### 声相

悬停在通道标签上可通过 tooltip 查看当前声相值。声相通过 MIDI CC10（Pan）自动控制。

### 4.4 MIDI 监视器

MIDI 监视器实时显示所有 MIDI 事件流，便于调试和学习 MIDI 数据。

#### 事件格式

每个事件显示为一行，格式为 `ChXX 类型 数据`，不同类型以颜色区分：

| 类型 | 颜色 | 显示内容 |
|------|------|----------|
| NoteOn | 绿色 | 通道、音高、力度 |
| NoteOff | 灰色 | 通道、音高 |
| CC | 蓝色 | 通道、控制器编号、值 |
| PB | 橙色 | 通道、弯音值 |
| PC | 紫色 | 通道、音色编号 |

示例输出：
```
Ch 1 NoteOn   60  vel:100
Ch 1 CC#7    val:80
Ch 2 PC      24
```

#### 过滤功能

- **Ch** — 通道过滤按钮（当前仅支持 All）
- **NoteOn / CC / PB / PC** — 点击切换对应类型的事件显示/隐藏

#### 工具栏

| 按钮 | 说明 |
|------|------|
| **Auto** | 自动滚动到最新事件 |
| **Clear** | 清空事件日志和统计 |
| **Copy** | 将当前可见事件复制到系统剪贴板 |

#### 状态栏

底部状态栏显示三项实时统计：

- **Events** — 总事件数（自上次 Clear 以来）
- **Notes** — 当前活跃音符数（已触发但未释放的 NoteOn）
- **事件率** — 每秒事件数（实时更新）

> 事件日志最多保留 500 条，超出后自动裁剪最早的记录。

### 4.5 Soundfont 浏览器

左栏显示当前加载的 SF2 音色库中的所有音色，按乐器分类组织。

- 搜索框支持按名称模糊搜索
- 分类标题可折叠/展开
- 点击音色条目可直接试听

> 需要在项目设置中配置默认 SoundFont（**项目 → 项目设置 → General → Clef → Default Soundfont**）。

---

## 5. JSON ↔ MIDI 转换

Clef 提供三种方式在 JSON 和 MIDI 之间互转。

### 方式一：顶部菜单

选中文件后：

- **项目 → Clef Utility → Compose MIDI from JSON...** — 将 `.json` 转换为 `.mid`
- **项目 → Clef Utility → Export MIDI to JSON...** — 将 `.mid` / `.tres` 导出为 `.json`

操作后会弹出保存对话框，选择输出位置即可。

### 方式二：文件系统右键菜单

在文件系统面板中右键点击文件：

- 右键 `.json`（Clef 格式）→ **Convert to MIDI**
- 右键 `.mid` / `.tres` → **Export to JSON**

> 只有符合 Clef JSON 格式的 `.json` 文件（包含 `format_version` 字段）才会显示 "Convert to MIDI" 选项。

### 方式三：Inspector 导出

选中 `MidiResource` 文件后，点击 Inspector 底部的 **Export JSON** 按钮。

### 往返一致性

JSON ↔ MIDI 转换是可逆的。导出为 JSON 后重新导入为 MIDI，音符、控制器、弯音、速度变化等数据保持一致。

> 注意：MIDI 格式本身的限制（如 running status、Meta Event 顺序）可能导致微小的二进制差异，但音乐内容不变。

---

## 6. MidiStreamPlayer 属性参考

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `midi_resource` | `MidiResource` | — | 要播放的 MIDI 资源 |
| `soundfont` | `String` | `""` | SF2 文件路径 |
| `loop` | `bool` | `false` | 循环播放 |
| `release_multiplier` | `float` | `1.0` | 释放时长倍率（0.1-2.0） |
| `autoplay` | `bool` | `false` | 场景就绪后自动播放 |
| `volume_db` | `float` | `-20.0` | 主音量（dB） |
| `pitch_scale` | `float` | `1.0` | 全局音高缩放 |
| `max_polyphony` | `int` | `64` | 最大同时发声数（1-128） |
| `bus` | `String` | `Master` | 输出音频总线 |

### 总线效果器

ClefMaster 总线提供三个内置效果器，通过 Inspector 调节参数：

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `reverb_enabled` | `bool` | `true` | 启用混响 |
| `reverb_room_size` | `float` | `0.29` | 混响房间大小（0-1） |
| `reverb_wet` | `float` | `0.15` | 混响湿信号比例（0-1） |
| `chorus_enabled` | `bool` | `true` | 启用合唱 |
| `chorus_wet` | `float` | `0.2` | 合唱湿信号比例（0-1） |
| `compressor_enabled` | `bool` | `false` | 启用动态压缩 |
| `compressor_threshold_db` | `float` | `-12.0` | 压缩阈值（-60~0 dB） |
| `compressor_ratio` | `float` | `4.0` | 压缩比（1~64） |
| `compressor_gain_db` | `float` | `0.0` | 补偿增益（-20~20 dB） |
| `eq_enabled` | `bool` | `false` | 启用 6 段均衡器 |

**效果器链顺序：** Compressor → EQ6 → Reverb → Chorus → 各通道 Panner

#### Compressor（动态压缩）

压缩超过阈值的信号峰值，防止多声部叠加时产生削波失真。

- **适用场景：** 多声部同时播放、游戏内多个音频源叠加时
- **压缩后音量可能降低：** 这是正常现象，通过 `compressor_gain_db` 拉回音量

#### EQ6（6 段均衡器）

调节不同频段的音量，用于音色修正和环境适配。

- **启用方式：** 勾选 `eq_enabled`，然后在编辑器的 **Audio** 面板中找到 ClefMaster 总线的 EQ6 调节各频段
- **适用场景：** 音色太亮/太暗、低频浑浊、需要为语音对话让出频段

#### SF2 离线 LPF

加载 SF2 音色库时，Clef 会自动读取每个采样的滤波器参数（filter_fc / filter_q）并在生成 AudioStreamWAV 时施加 biquad 低通滤波。这是一个一次性预处理步骤，不影响运行时性能。

> 并非所有 SF2 采样都定义了滤波参数。未定义时（filter_fc < 0 或 ≥ 20000 Hz）会自动跳过。

### 信号

| 信号 | 参数 | 说明 |
|------|------|------|
| `note_triggered` | `channel, pitch, velocity` | 每次触发音符时发出 |
| `finished` | — | 非循环模式播放结束时发出 |

---

## 7. 脚本 API

### 基本播放

```gdscript
@onready var player: MidiStreamPlayer = $MidiStreamPlayer

func _ready():
    player.start_playback()
    player.finished.connect(_on_song_end)

func _on_song_end():
    print("播放结束")
```

### 暂停与跳转

```gdscript
func _input(event):
    if event.is_action_pressed("pause"):
        if player.is_playing():
            player.pause()
        else:
            player.resume()
    if event.is_action_pressed("skip"):
        player.seek(player.get_playback_position() + 5.0)
```

### 运行时切换 MIDI 资源

```gdscript
func switch_song(new_song: MidiResource):
    if player.is_playing():
        player.stop()
    player.midi_resource = new_song
    player.start_playback()
```

### 运行时切换 SoundFont

```gdscript
func switch_soundfont(path: String):
    player.soundfont = path
```

---

## 8. LLM 辅助编曲

Clef 提供两种 LLM 辅助作曲方式：**Clef Compose**（推荐，基于 Claude Code 多 Agent 协作）和 **模板编曲**（手动将 JSON 提交给任意 LLM）。

### 方式一：Clef Compose（推荐）

在 Claude Code 中使用 `/clef-compose` 命令，用自然语言描述音乐需求即可自动生成 MIDI。系统通过 7 个专业 Agent 协作完成：旋律创作 → 和声编配 → 节奏设计 → 表现力注入 → 质量评审 → 自动迭代 → MIDI 输出。

使用示例：

```
/clef-compose 帮我写一段 boss 战斗音乐，D大调，140BPM，30秒，管弦风格
```

详细用法参见 [LLM 作曲使用指南](user_docs/llm_midi_composer_guide_cn.md)。

### 方式二：模板编曲

将 [系统提示词](user_docs/celf_composer_llm_system_prompt_cn.md) 和 [模板文件](../templates/) 提供给 ChatGPT / Claude 等 LLM，手动完成 JSON → MIDI 转换。

使用流程：

1. 将 [templates/default.json](../templates/default.json) 作为起始模板
2. 向 LLM 描述你的需求，附带系统提示词
3. LLM 返回 Clef JSON
4. 在 Godot 中使用编辑器工具（右键 `.json` → Convert to MIDI）转换为 MIDI
5. 在 Inspector 中预览试听

#### 模板文件

| 文件 | 用途 |
|------|------|
| `templates/default.json` | 最小有效 JSON，适合快速测试 |
| `templates/example_full.json` | 完整示例，包含多轨、CC、弯音、速度变化 |
| `templates/llm_compose_guide.json` | 精炼规范速查表 |

---

## 9. Python 工具链

Clef 提供一组 Python 脚本（位于 `.claude/skills/clef-compose/scripts/`），通过 `clef_tools.py` 统一入口调用。

### midi-to-audio — MIDI 转音频

使用 FluidSynth 将 MIDI 文件渲染为 WAV，可选转 OGG 或 MP3。

```bash
# 单文件转 WAV
python clef_tools.py midi-to-audio song.mid --sf2 soundfont.sf2

# 转 OGG 格式
python clef_tools.py midi-to-audio song.mid --sf2 soundfont.sf2 -f ogg -o output/

# 批量转换目录下所有 MIDI
python clef_tools.py midi-to-audio ./midis/ --sf2 soundfont.sf2 --batch -f ogg

# 自定义采样率
python clef_tools.py midi-to-audio song.mid --sf2 soundfont.sf2 -r 48000
```

**依赖：**
- `fluidsynth`（必需）— [安装指南](https://github.com/FluidSynth/fluidsynth/wiki/Download)
- `ffmpeg`（OGG/MP3 格式需要）

### 其他子命令

| 子命令 | 说明 |
|--------|------|
| `check-deps` | 检查 Python 依赖是否安装 |
| `abc-to-midi` | ABC 记谱法 → MIDI 转换 |
| `validate` | music21 技术验证（调性/音域/时值/对齐/重叠） |
| `merge` | 合并多声部 ABC 片段 |
| `inject` | 注入 CC/弯音到 MIDI |
| `extract-solo` | 分轨 Solo 提取 |
| `analyze` | MIDI 结构分析报告 |
| `snapshot` | 备份 score.abc + 步骤日志 |
| `archive` | 归档最终产出到 output/ |

---

## 10. 常见问题

### Q: 播放没有声音？

检查以下几点：
1. 是否配置了 SoundFont（项目设置 → Clef → Default Soundfont）
2. `volume_db` 默认为 -20.0，不是静音但音量较小
3. 确认音频总线未静音

### Q: Inspector 预览报错 "placeholder instance"？

这是 Godot 编辑器的已知行为。Clef 已处理此问题，如果仍然遇到，请尝试重新选中资源文件。

### Q: 循环播放时有停顿？

Clef 在所有事件处理完毕后立即循环，正在释放的音符会自然衰减。如果最后一个音符的 release 时间很长，可能与新循环开头重叠——这是正常行为。

### Q: 如何调整复音数？

修改 `max_polyphony` 属性。默认 64，范围 1-128。降低复音数可节省内存，但可能导致音符被窃取。

### Q: 支持哪些 MIDI 功能？

支持标准 MIDI Channel Messages（Note、Program Change、Control Change、Pitch Bend）和部分 Meta Events（Tempo Change）。不支持 SysEx 和 MIDI 时钟消息。
