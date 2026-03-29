# Clef 用户手册

## 目录

1. [安装与配置](#1-安装与配置)
2. [播放 MIDI 文件](#2-播放-midi-文件)
3. [Inspector 预览](#3-inspector-预览)
4. [JSON ↔ MIDI 转换](#4-json--midi-转换)
5. [MidiStreamPlayer 属性参考](#5-midistreamplayer-属性参考)
6. [脚本 API](#6-脚本-api)
7. [LLM 辅助编曲](#7-llm-辅助编曲)
8. [常见问题](#8-常见问题)

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
   - **⏹ Stop** — 停止播放
   - 进度条 — 显示当前播放进度
   - **Export JSON** — 导出为 Clef JSON 格式

> 前提：已在项目设置中配置了默认 SoundFont。

---

## 4. JSON ↔ MIDI 转换

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

## 5. MidiStreamPlayer 属性参考

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `midi_resource` | `MidiResource` | — | 要播放的 MIDI 资源 |
| `soundfont` | `String` | `""` | SF2 文件路径 |
| `loop` | `bool` | `false` | 循环播放 |
| `release_multiplier` | `float` | `1.0` | 释放时长倍率（0.1-2.0） |
| `autoplay` | `bool` | `false` | 场景就绪后自动播放 |
| `volume_db` | `float` | `-20.0` | 主音量（dB） |
| `pitch_scale` | `float` | `1.0` | 全局音高缩放 |
| `max_polyphony` | `int` | `32` | 最大同时发声数（1-128） |
| `bus` | `String` | `Master` | 输出音频总线 |

### 信号

| 信号 | 参数 | 说明 |
|------|------|------|
| `note_triggered` | `channel, pitch, velocity` | 每次触发音符时发出 |
| `finished` | — | 非循环模式播放结束时发出 |

---

## 6. 脚本 API

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

## 7. LLM 辅助编曲

Clef JSON 格式专为 LLM 辅助作曲设计。将 [系统提示词](user_docs/celf_composer_llm_system_prompt_cn.md) 提供给 ChatGPT / Claude 等 LLM，即可进行 AI 辅助作曲。

### 工作模式

LLM 支持三种模式：

1. **创作** — 描述你想要的音乐（风格、情绪、时长），LLM 生成 Clef JSON
2. **分析** — 提供已有的 Clef JSON，LLM 分析其风格、配器、结构
3. **参考编曲** — 提供参考 JSON + 新需求，LLM 基于参考进行改编

### 使用流程

1. 将 [templates/default.json](../templates/default.json) 作为起始模板
2. 向 LLM 描述你的需求
3. LLM 返回 Clef JSON
4. 在 Godot 中使用编辑器工具转换为 MIDI
5. 在 Inspector 中预览试听

### 模板文件

| 文件 | 用途 |
|------|------|
| `templates/default.json` | 最小有效 JSON，适合快速测试 |
| `templates/example_full.json` | 完整示例，包含多轨、CC、弯音、速度变化 |
| `templates/llm_compose_guide.json` | 精炼规范速查表 |

---

## 8. 常见问题

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

修改 `max_polyphony` 属性。默认 32，范围 1-128。降低复音数可节省内存，但可能导致音符被窃取。

### Q: 支持哪些 MIDI 功能？

支持标准 MIDI Channel Messages（Note、Program Change、Control Change、Pitch Bend）和部分 Meta Events（Tempo Change）。不支持 SysEx 和 MIDI 时钟消息。
