---
name: theory-abc
description: ABC 记谱法语法参考。包含头部字段、音符语法、和弦记谱、多声部、MIDI 指令、力度标记、GM 鼓组映射。供所有 clef agent 共用。
user-invocable: false
---

## ABC 记谱法参考

ABC 记谱法是 clef-compose v2 的核心输出格式，所有 Agent 使用 ABC 表示音符、和弦和节奏。

### ABC 头部字段

| 字段 | 格式 | 说明 | 示例 |
|------|------|------|------|
| X: | `X:<编号>` | 曲目编号（必须第一行） | `X:1` |
| T: | `T:<标题>` | 曲目标题 | `T:Battle Theme` |
| M: | `M:<拍号>` | 拍号 | `M:4/4` `M:3/4` `M:6/8` |
| L: | `L:<时值>` | 默认音符时值 | `L:1/4`（四分音符） `L:1/8` |
| Q: | `Q:<速度>` | 速度（BPM） | `Q:1/4=120` |
| K: | `K:<调号>` | 调号 | `K:D` `K:Am` `K:Bb` |

> **调号格式注意**：大调直接写字母（`K:D`），小调加 `m`（`K:Am`）。不要写 `K:Dmaj` 或 `K:Amin`。

### 音符语法

| 元素 | 写法 | 含义 |
|------|------|------|
| 基本音 | `C` `D` `E` `F` `G` `A` `B` | 白键音（大写 = 中央八度以下） |
| 升号 | `^C` `^F` | 升半音（前缀 `^`） |
| 降号 | `_B` `_E` | 降半音（前缀 `_`） |
| 高八度 | `c` `d` `e` | 小写 = 高一个八度 |
| 更高八度 | `c'` `d''` | 撇号 = 继续升高 |
| 低八度 | `C,` `D,,` | 逗号 = 降低八度（每逗一个） |
| 休止 | `z` | 休止符 |
| 时值 | `C2` `A/2` | 数字 = 乘（`C2` = 二分音符），`/` = 除（`A/2` = 八分音符） |
| 附点 | `C3/2` | 附点音符（原时值 ×1.5） |
| 连音 | `(3cde` | 三连音（`(3` 前缀） |

> **⚠️ Agent 必读：L:1/8 时值换算速查**
>
> 当 `L:1/8` 时，默认单位 = 八分音符 = **0.5 拍**（四分音符 = 1 拍）。
> 数字后缀表示「乘以该单位的几倍」。
>
> | ABC 写法 | 计算 | 实际拍数 | 音乐含义 |
> |----------|------|---------|---------|
> | `d` | 1 × 0.5 | 0.5 拍 | 八分音符 |
> | `d2` | 2 × 0.5 | 1 拍 | 四分音符 |
> | `d4` | 4 × 0.5 | 2 拍 | 二分音符 |
> | `d6` | 6 × 0.5 | 3 拍 | 附点二分音符 |
> | `d8` | 8 × 0.5 | 4 拍 | 全音符 |
> | `d/2` | 0.5 × 0.5 | 0.25 拍 | 十六分音符 |
>
> **4/4 拍一满小节 = 4 拍 = 8 个八分音符时值**
>
> 常见错误：误以为 `d4` = 4 拍。实际上 `d4` = **2 拍**（二分音符），`d8` 才是 4 拍。

### 和弦记谱

使用方括号将多个音组合为同时发声的和弦：

```
[CEG]     → C 大三和弦
[FAc]     → F 大三和弦（跨八度）
[_BDF]    → Bdim 减三和弦
[CEG2]    → 和弦持续二分音符时值
```

### 多声部（Voice）

使用 `V:` 声明独立声部，每个声部可指定不同谱号和 MIDI 参数：

```
V:1 name="Melody" clef=treble
V:2 name="Chords" clef=bass
V:3 name="Drums" clef=perc
```

### MIDI 指令

在声部声明后追加 MIDI 参数控制通道和音色：

> **Channel 编号说明**：ABC `%%MIDI channel` 使用 0-indexed（0-15），即 channel 9 = MIDI Channel 10（GM 标准鼓组通道）。下文所有 `channel 9` 均指 GM Channel 10。

```
V:1 name="Melody" clef=treble
%%MIDI channel 1
%%MIDI program 80        ← Square Lead

V:3 name="Drums" clef=perc
%%MIDI channel 9
%%MIDI program 0         ← 打击乐固定 0（GM Channel 10）
```

### 力度标记

嵌入在音符前或独立行使用：

| 标记 | 含义 | ABC 写法 |
|------|------|---------|
| pp | 极弱 | `!pp!` |
| p | 弱 | `!p!` |
| mp | 中弱 | `!mp!` |
| mf | 中强 | `!mf!` |
| f | 强 | `!f!` |
| ff | 极强 | `!ff!` |

### 小节线

| 符号 | 含义 |
|------|------|
| `\|` | 小节线 |
| `\|\|` | 双小节线（段落边界） |
| `\|:` | 反复开始 |
| `:\|` | 反复结束 |
| `\|1` / `\|2` | 第一/二结尾 |

### GM 鼓组映射（Rhythmist Agent 专用）

鼓组声部（`clef=perc`，ABC channel 9 = MIDI Channel 10）使用以下 ABC 音符对应 GM 打击乐：

| ABC 记谱 | 音色 | MIDI Note | 节奏功能 |
|----------|------|-----------|---------|
| `B,,` | Kick (低音鼓) | 36 | 主干，重拍 |
| `D,` | Snare (军鼓) | 38 | 主干，反拍 |
| `c` | Closed Hi-Hat (闭镲) | 42 | 主干，律动感 |
| `d` | Open Hi-Hat (开镲) | 46 | 点缀，节奏变化 |
| `F,` | Low Tom (低汤姆) | 45 | 填充，过渡 |
| `A,` | High Tom (高汤姆) | 50 | 填充，过渡 |
| `a` | Crash (吊镲) | 49 | 标记，段落开始/高潮 |
| `g` | Ride (叮叮镲) | 51 | 主干，稳定律动 |

> 鼓组声部的 `%%MIDI channel` 必须为 `9`（= MIDI Channel 10），`%%MIDI program` 必须为 `0`。

### 完整示例

```
X:1
T:Battle Theme
M:4/4
L:1/8
Q:1/4=140
K:D

V:1 name="Melody" clef=treble
%%MIDI channel 1
%%MIDI program 56
|: d2 f2 a2 f2 | a4 g2 f2 :|
|: d2 ^f2 a2 g2 | f4 d2 z2 :|

V:2 name="Chords" clef=bass
%%MIDI channel 2
%%MIDI program 48
| [DF,A,]4 [DFA]4 | [G,B,D]4 [G,B,d]4 |
| [DF,A,]4 [DFA]4 | [CEG]4 [CEG]4 |

V:3 name="Drums" clef=perc
%%MIDI channel 9
%%MIDI program 0
| B,,z D,z B,,z z2 | B,,z D,z B,,z D,z |
| B,,z D,z B,,z z2 | B,,z D,z a4 |
```
