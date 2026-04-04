# miditools 算法思路调查

> 调查 `E:\GitHub\miditools`（Peter J Billam 的 MIDI 工具集）中对 clef-compose 和 clef Godot 插件有参考价值的算法思路。
> 日期：2026-04-04

## 结论概要

miditools 是一套 Perl/Lua 工具集，大部分依赖 Linux ALSA 实时 MIDI，与 clef 的 Python/GDScript 技术栈不兼容，无法直接移植。但有 **3 个算法思路** 值得借鉴：

1. **N 阶 Markov 链旋律生成**（midimarkov）
2. **12 音 bitmap 和弦检测与外音修正**（midichord）
3. **分形序列用于节奏模式生成**（sequence）

---

## 1. N 阶 Markov 链旋律生成（midimarkov）

**来源**：`midimarkov`（Lua）、`midi_markov.lua`（Lua 库）

### 核心算法

从已有 MIDI 文件中提取音符序列，构建多阶转移概率表，然后随机游走生成新旋律。

**训练阶段**：

1. 将 MIDI 转为"词"序列（音高 + 时值的字符串拼接）
2. 维护 N 层转移表（默认 N=4），`statetab[i]` 存储最后 i 个词的转移列表
3. 每读入一个词，插入到所有 i 层表中：`prefix(w, i) -> [候选词1, 候选词2, ...]`

**生成阶段**：

1. 从种子词开始（或用 `#` 占位符初始化）
2. 从最高阶（N=4）开始查找候选列表
3. 若 N=4 的候选数 > 1，随机选一个（保持局部风格）
4. 若 N=4 候选不足（<= 1），降级到 N=3，依此类推到 N=1
5. 窗口滑动：丢弃最旧词，追加新词

```python
# 伪代码（Python 改写思路）
for i in range(depth, 0, -1):
    candidates = statetab[i][prefix(window, i)]
    if candidates and len(candidates) > 1:
        next_word = random.choice(candidates)
        break
# 降级机制确保不会死循环
```

### 和弦感知的 Markov（未完成但思路值得注意）

midimarkov 的 TODO 中提出维护 **3 种和声链**，从具体到抽象：

1. **绝对和声链**：如 `43,53,59,68 -> -1,0,+1,0`（实际音高的音程变化）
2. **八度化和声链**：如 `0,10,6,9 -> -1,0,+1,0`（模 12 后的音程）
3. **规范和声链**：如 `0,2,3,3 -> -1,0,0,+1`（音阶度数变化）

核心思想：用音程差而非绝对音高作为 Markov 状态，使模型能识别跨调号的和声模式。

### 对 clef-compose 的启发

- **风格模仿功能**：可以让用户提供一个参考 MIDI，训练 Markov 模型后生成风格相似的新旋律
- **旋律补全**：给定前几个小节的 ABC，用 Markov 模型续写后续旋律
- **节奏模板分离**：midimarkov 支持 `-R rhythmfile.mid` 参数，节奏文件被原样复用而不参与 Markov 训练。这与 clef 的 V:4 鼓声部思路一致

### 局限

- 纯统计模型，无音乐理论约束，可能生成不协和音程
- 无多声部协调能力
- 生成的旋律缺乏整体结构（ABA、起承转合）

---

## 2. 12 音 bitmap 和弦检测与外音修正（midichord）

**来源**：`midichord`（Perl），约 41KB

### 核心算法

实时或离线地将"可调通道"的音符修正为符合"固定通道"当前和弦的音符。

**和弦表示**：

```perl
my @ReigningChord = (0,0,0,0,0,0,0,0,0,0,0,0);  # c..b = 0..11
```

用一个 12 元素数组表示当前"执政和弦"，索引为音级（C=0 到 B=11），值为 1 表示该音级属于当前和弦。

**和弦更新**：当固定通道的 note_on 事件到来时，根据当前发声的所有音符重新计算 ReigningChord（实际上是"当前正在响的音符集合"，非传统和声分析）。

**音符修正策略**（3 种可选）：

1. **模 12 修正（-am modulus）**：将音符 mod 12 到最近的和弦音。简单粗暴，音高跳跃大
2. **最近和弦音修正（-ac closest）**：向上或向下找到最近的和弦音级，取半音距离最小的
3. **最近和弦音无延留（-at truncate）**：同上，但和弦变化时立即截断与新和弦矛盾的延留音

```python
# 最近和弦音修正的伪代码
def closest_chord_note(note, reigning_chord):
    for offset in range(1, 13):
        for direction in [1, -1]:
            candidate = (note + direction * offset) % 12
            if reigning_chord[candidate]:
                return note + direction * offset
    return note  # fallback
```

### 对 clef-compose 的启发

- **validate_abc.py 增强**：当前验证器检查音域和跳跃，但未检查和声一致性。可以用类似 bitmap 方案验证 V:1 旋律音是否属于 V:2 和声声部当前暗示的和弦
- **Rhythmist 低音修正**：V:3 低音线可以用此算法确保低音音符合当前和弦根音或五度
- **实时和弦跟随**：如果 Godot 插件未来支持实时 MIDI 输入，此算法可用于"和弦跟随"功能

### 局限

- "和弦"= 当前发声音符集合，不是真正的和声分析（无法识别 Am7 vs C）
- 修正策略过于简单，不考虑和弦音的排列位置（根音/三音/五音）

---

## 3. 分形序列用于节奏模式生成（sequence）

**来源**：`sequence`（Perl），约 8KB

### 核心算法

提供 5 种数学序列，将 K 个元素按特定规则扩展为 N 个元素的序列。原本设计用于将短音频片段拼接成有趣的节奏模式。

**5 种序列**：

| 序列 | 算法 | 特点 |
|------|------|------|
| **Cycle** | 简单循环 `A B C A B C ...` | 最基础，无创造性 |
| **Morse-Thue** | Leibnitz 序列 mod K | 分形、自相似、非周期 |
| **Rabbit** | 替换规则 `0->01, 1->0`, Fibonacci 类 | 自相似，类似斐波那契 |
| **Leibnitz** | 递归叠加+偏移 | 分形，log(K) 复杂度 |
| **Push-and-Half-Shift** | 滑动窗口扩展 | 从首元素渐变到末元素 |

**Morse-Thue 示例**（K=2, A/B）：
```
A B B A B A A B B A A B A B B A
```
递归生成：`0 -> 0 1 -> 0 1 1 0 -> 0 1 1 0 1 0 0 1 -> ...`

**Push-and-Half-Shift 示例**（6 个音符 A-F）：
```
A A B B C B C D C D E C D E F C D E F D E F D E F E F E F F
```
渐变效果：从纯 A 开始，逐步引入 B、C、D...，最终以 F 为主。

### 对 clef-compose 的启发

- **节奏模式生成**：Rhythmist Agent 可以用 Morse-Thue 序列将 2 个基本节奏型（如"四分+四分"和"八分+八分"）扩展为 16 小节的节奏结构，产生非循环但有内聚力的节奏
- **动态变化曲线**：Push-and-Half-Shift 的"从 A 渐变到 F"特性可以用于 Orchestrator 的 CC7（音量）自动化曲线，实现从 pp 到 ff 的渐进式动态变化
- **段落结构**：Rabbit 序列的自相似特性（类似黄金分割）可用于生成乐段长度的比例关系

### 局限

- 生成的序列不感知音乐节拍和小节线
- 需要将抽象序列映射到具体的节奏值（映射规则需自行设计）

---

## 其他工具（低价值）

| 工具 | 说明 | 不适用的原因 |
|------|------|-------------|
| MIDI.py | Python MIDI 解析库（midi2score/score2midi） | clef 已用 mido，功能重叠 |
| midifade | CC 自动化（音量/泛音/滤波器） | ALSA curses UI，clef 的 expression_plan.json 已覆盖 |
| midisox | MIDI 版的 sox（变速/变调/拼接） | Linux CLI 管道模型，Godot 插件无法调用 |
| midi2muscript | MIDI -> muscript 记谱 | 输出格式不兼容 ABC |
| musicxml2mid | MusicXML -> MIDI | 仅单向转换，clef 不需要 MusicXML 输入 |
| bassline | 和弦进行 -> 低音线 | 算法过于简单（仅琶音模式） |
| midiedit | curses MIDI 编辑器 | 完整的 TUI 应用，无法复用 |
| audio2midi | 音频 -> MIDI | 依赖外部 DSP，Python 重写代价大 |

---

## 建议的下一步

优先级从高到低：

1. **Markov 风格模仿**（midimarkov 思路）—— 作为 clef-compose 的可选功能，用户上传参考 MIDI 后训练模型，生成风格相似的旋律。预计实现量：200-300 行 Python
2. **和弦一致性验证**（midichord bitmap 思路）—— 在 `validate_abc.py` 中增加一项检查，验证旋律音与同时刻和弦音的协和度。预计实现量：50-100 行 Python
3. **分形节奏生成**（sequence 思路）—— 在 theory-rhythm 乐理参考中增加 Morse-Thue/Rabbit 序列模板，供 Rhythmist Agent 使用。预计实现量：纯文档，无需代码
