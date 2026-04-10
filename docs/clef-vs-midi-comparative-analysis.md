# Clef vs addons/midi 播放质量对比分析

**日期**: 2026-04-10
**分析者**: Claude Code (Subagent-Driven Analysis)
**对比版本**: Clef (commit `2f0952b`) vs addons/midi (arlez80)
**修复版本**: commit `959f6af` 已修复 P0 全部 + P1 全部，见各章节 `[已修复]` 标注

**状态标记**:
- `[已对比]` = 代码级交叉审查完成
- `[已修复]` = 代码已修改（commit `959f6af`）
- `[待听感验证]` = 需在 Godot 中播放验证实际听感
- `[未对比]` = 尚未深入分析

---

## 1. 概述

本报告系统性地对比了 Clef 插件 (`addons/clef/`) 与 addons/midi 插件 (`addons/midi/`) 的 MIDI 播放链路，定位音色还原度差异的根本原因。

**分析范围**: SF2 解析、采样制备、音高计算、ADSR 包络、通道状态、总线效果器、声部分配、小提琴短音符专项。

**关键发现**: 共发现 **1 个 Critical、5 个 High、7 个 Medium** 级差异。最突出的问题是 commit `2f0952b`（multi-zone layering）引入的 **legato 逻辑丢失回归 bug**，直接影响小提琴等持续乐器的快速连奏听感。

---

## 2. 架构对比总览

| 维度 | Clef | addons/midi | 差异 | 状态 |
|------|------|-------------|------|------|
| 音频后端 | AudioStreamPlayer + pitch_scale | AudioStreamPlayer + pitch_scale | 相同 | [已对比] |
| SF2 解析 | 四层 Generator 累积 | 三层（缺 preset global zone） | Clef 更完整 | [已对比] |
| 采样制备 | 按需提取，head silence 125ms | 加载时全量，head silence 125ms | 基本相同 | [已对比] |
| Multi-zone | ✅ (2f0952b) | ✅ | 相同 | [已对比] |
| 立体声 | Godot 原生交错立体声 | 双 bus 独立 L/R | 各有优劣 | [已对比] |
| ADSR | 5 状态 (A/H/D/S/R) | 3 状态 (A/D/R) | Clef 多 Hold | [已对比] |
| 声部数 | ~~32 (cap 8)~~ **64 (cap 16)** | 96 (无 cap) | 差异缩小 | [已修复] |
| Legato | ~~丢失~~ **已恢复** | 无 | Clef 更优 | [已修复] |
| 效果器 | ~~全局~~ **Per-channel** Reverb/Chorus + Compressor/EQ | Per-channel Reverb/Chorus | 已对齐 | [已修复] |
| CC91/CC93 | ~~不支持~~ **已支持** | 支持 | 已对齐 | [已修复] |
| 复音补偿 | ~~无~~ **已添加** (layer_count) | 有 (/polyphony_count) | 已对齐 | [已修复] |

---

## 3. SF2 采样制备差异

### 3.1 Head Silence — 无差异 [已对比]
- Clef: `HEAD_SILENT_SAMPLES = 5512` (125ms) (`clef_bank.gd:7`)
- addons/midi: `head_silent_samples = 44100/8 = 5512` (`Bank.gd:154-156`)
- **影响**: 无

### 3.2 采样率校正 — 无差异 [已对比]
- 两者均使用 `log(sample_rate/44100)/log(2)` 作为 pitch offset 校正
- Clef: `clef_bank.gd:114-115`
- addons/midi: `Bank.gd:421-424`
- **影响**: 无

### 3.3 Loop 处理 — Medium [已对比] [P2 待修复]
- **Clef**: 鼓组一律强制禁用 loop (`is_drum` → `has_loop = false`)
- **addons/midi**: 对立体声采样有 heuristic loop 检测：`start + 64 <= start_loop && sample_modes == -1 && !drum` (`Bank.gd:435`)
- **影响**: 某些鼓组循环采样（如 hi-hat loop）在 Clef 中无法正确循环
- **修复**: 为非鼓组采样添加 `sample_modes == -1` 时的 heuristic fallback

### 3.4 立体声分离 — 架构差异 [已对比]
- **Clef**: L/R 交错为单个 `AudioStreamWAV(stereo=true)`，使用 Godot 原生立体声播放
- **addons/midi**: L/R 分为两个独立 mono `AudioStreamWAV`，通过独立 Audio bus 实现声像
- **影响**: Clef 方案音质更好、延迟更低；addons/midi 方案支持运行时声像调整。Clef 对立体声采样的 CC10 声像控制不够精确（见 §6.3）

### 3.5 Generator 累积 — Clef 更完整 [已对比]
- **Clef**: 完整四层累积 (Preset Global → Preset Local → Inst Global → Inst Local)
- **addons/midi**: 三层累积，**缺少 preset global zone** 的 coarse/fine tune
- **影响**: 对大多数 SF2 文件无影响（preset global zone 较少使用），但复杂音色库可能产生偏差

### 3.6 Zone 匹配优先级 [已对比]
- **Clef**: "最具体优先" (key_range 窄 > vel_range 窄)
- **addons/midi**: "全部叠加" (遍历所有匹配的 instrument)
- **影响**: Clef 更符合 SF2 规范，无需修改

---

## 4. 音高计算差异

### 4.1 base_pitch 组成 — Low [已对比]
- **Clef**: `tuning_cents/1200 + log2(sr/44100)`，tuning_cents 含四层 zone 累积
- **addons/midi**: `(coarse_tune)/12 + (fine_tune + pitch_correction)/1200 + log2(sr/44100)`，三层累积
- **影响**: 对使用 preset global zone 的 SF2 可能有微小偏差，实际听感影响不大

### 4.2 Pitch Bend 归一化 — High [已对比] [Clef 行为正确，无需修复]
- **Clef**: `_pitch_bend ∈ [-1, +1]`，归一化后的值 (`channel_state.gd`)
- **addons/midi**: `pitch_bend ∈ [-8192, +8192]`，原始 14-bit 值
- **计算差异**:
  - Clef: `bend * sensitivity / 12` (sensitivity 默认 2，弯音范围 ±2 半音)
  - addons/midi: `bend * sensitivity / 12` (sensitivity 默认 12，但 raw 值未归一化时范围极大)
- **影响**: 需确认 addons/midi 的调用方是否正确传入归一化后的值。若传入 raw 值则弯音范围异常
- **Clef 处理**: `midi_stream_player.gd` 中对 raw pitch bend 做了 `(value - 8192) / 8192.0` 归一化，行为正确

### 4.3 Modulation/Vibrato — Low [已对比]
- **Clef**: `sin(t * 32) * modulation * sensitivity / 12`，sensitivity 默认 **0.25**
- **addons/midi**: `sin(t * 32) * modulation * sensitivity / 12`，sensitivity 默认 **0.5**
- **影响**: addons/midi 默认颤音深度是 Clef 的 2 倍。CC1=64 时 Clef 颤音幅度明显小于 addons/midi

---

## 5. ADSR 包络差异

### 5.1 Attack 阶段 — 无差异 [已对比]
- 两者均使用线性振幅插值
- Clef: `linear_to_db(lerpf(db_to_linear(-144), 1.0, t))` (`clef_voice.gd:277`)
- addons/midi: `linear_to_db(lerpf(db_to_linear(prev), db_to_linear(next), t))` (`ADSR.gd:184`)

### 5.2 Hold 阶段 — Medium (Clef 优势) [已对比]
- **Clef**: 有独立 HOLD 状态 (`clef_voice.gd:283-290`)
- **addons/midi**: 无 Hold 阶段，attack 结束后直接进入 decay
- **影响**: 使用 SF2 hold 时间的音色（如某些合成 pad），Clef 能正确保持满音量一段时间

### 5.3 Decay 插值 — Medium [已对比] [P2 待修复]
- **Clef**: 线性振幅插值 `lerpf(1.0, db_to_linear(sustain_db), t)` (`clef_voice.gd:293`)
- **addons/midi**: 线性 dB 插值 `lerpf(0.0, sustain_db, t)` (`ADSR.gd:187`)
- **影响**: Clef 的 decay 感知上更均匀（线性振幅 = 匀速衰减），addons/midi 的 decay 前段急后段缓（线性 dB）。对持续音色听感有可察觉差异

### 5.4 Release 阶段 — Medium [已对比]
- 两者均使用线性 dB 插值
- **Clef**: 从当前实际音量 (`_release_start_db`) 开始释放 (`clef_voice.gd:305`)
- **addons/midi**: 从固定 sustain level 开始释放 (`ADSR.gd:187`)
- **影响**: staccato 等提前释放场景，Clef 从当前电平平滑淡出更自然；addons/midi 可能跳变到 sustain level 再淡出

### 5.5 复音补偿 — High ~~[Clef 缺失]~~ [已修复 959f6af]
- **Clef**: 无复音补偿
- **addons/midi**: `volume_db = linear_to_db(db_to_linear(v) / polyphony_count)`，立体声额外 `/2` (`ADSR.gd:213-218`)
- **影响**: multi-zone 叠加时（如小提琴 2 层），Clef 无补偿导致音量偏高约 +6dB；多声部齐奏时可能导致削波失真

### 5.6 Velocity 到音量映射 — 无差异 [已对比]
- 两者均为 `linear_to_db(velocity / 127.0)`

### 5.7 非循环采样预释放 — Clef 优势 [已对比]
- **Clef**: 在采样结束前 50ms (`_PRE_RELEASE_MARGIN`) 触发平滑淡出 (`clef_voice.gd:79-83, 250-269`)
- **addons/midi**: 依赖外部 `auto_release_mode` 标志，由调度器触发释放 (`ADSR.gd:177`)
- **影响**: Clef 对打击乐、钢琴衰减音等非循环采样的尾部处理更平滑

---

## 6. 通道状态与效果器差异

### 6.1 CC 支持对比表

| CC | 功能 | Clef | addons/midi | 差异 |
|----|------|------|-------------|------|
| CC1 | Modulation | ✅ sensitivity=0.25 | ✅ sensitivity=0.5 | Low | [已对比] |
| CC7 | Volume | ✅ | ✅ | 无 | [已对比] |
| CC10 | Pan | ✅ | ✅ | 无 | [已对比] |
| CC11 | Expression | ✅ | ✅ | 无 | [已对比] |
| CC64 | Sustain | ✅ voice 级拦截 | ✅ ADSR 级拦截 | Medium | [已对比] [P2] |
| **CC91** | **Reverb Send** | **✅ [已修复]** | **✅** | ~~High~~ 已对齐 | [已修复] |
| **CC93** | **Chorus Send** | **✅ [已修复]** | **✅** | ~~High~~ 已对齐 | [已修复] |
| CC5/65/84 | Portamento | ❌ | 部分（仅存储） | Medium | [已对比] |

### 6.2 总线效果器架构 — ~~High~~ 已修复 [已对比]

**Clef 架构 (修复后)**:
```
ClefMaster Bus: [Compressor] → [EQ6]
  └── clef_ch_N: [Panner] → [Reverb] → [Chorus]
```
- Reverb/Chorus 已移到 **per-channel 总线**，由 CC91/CC93 独立控制
- Compressor 和 EQ6 保留在 ClefMaster（全局动态控制）

**addons/midi 架构**:
```
midi_ch_N: [Chorus] → [Panner] → [Reverb]
  ├── midi_ch_N_left: [Panner pan=-1.0]
  └── midi_ch_N_right: [Panner pan=+1.0]
```
- 每个通道有**独立**的 Reverb/Chorus 效果器
- CC91/CC93 控制 per-channel 湿信号比例
- 立体声子总线实现精确声像分离

### 6.3 立体声声像处理 — High [已对比] [P2 待修复]
- **Clef**: 通道总线挂单个 AudioEffectPanner，CC10 直接修改 pan。立体声采样通过单总线处理
- **addons/midi**: 左/右声道分别路由到独立子总线（Panner pan=±1.0），CC10 控制主总线 Panner
- **影响**: Clef 对立体声采样（如钢琴）的声像控制不精确，CC10 旋转整个立体声声像而非调整左右平衡

### 6.4 Reverb 参数默认值 [已对比] [已修复]
- **Clef (修复后)**: per-channel reverb，wet 由 CC91 × reverb_wet 控制（默认 reverb_wet=0.15）；predelay=15ms, room_size=0.29, damping=0.3, hipass=0.05
- **addons/midi**: per-channel reverb，wet 由 CC91 × reverb_power 控制（默认 reverb_power=0.5）；其他用 Godot 默认值
- **影响**: 修复后两者均支持 per-channel 控制，Clef 的混响参数仍更紧凑自然

### 6.5 Sustain Pedal (CC64) — Medium [已对比] [P2 待修复]
- **Clef**: voice 级别拦截 — `_sustained=true` 阻止 `stop_note()`；踏板释放时直接调用所有 voice 的 `stop_note()`
- **addons/midi**: ADSR 级别拦截 — `hold=true` 阻止进入 release 状态；踏板释放后 ADSR 自然过渡到 release
- **影响**: addons/midi 的延音释放通过 ADSR 状态机过渡更自然

---

## 7. 声部分配差异

### 7.1 声部数与容量 — ~~High~~ 已修复 [已对比]

| 参数 | Clef (修复后) | addons/midi |
|------|------|-------------|
| 总声部数 | **64** | 96 (可扩至 256) |
| 每通道上限 | **16** | 无限制 |
| Multi-zone 消耗 | 2 声部/音符 | 2 声部/音符 |

**瓶颈分析 (修复后)**: 2 zone 乐器 + 16/通道 cap = 每通道最多 8 音符同时发声，可满足大多数管弦乐场景。与 addons/midi 的 96 声部仍有差距但已大幅改善。

### 7.2 Stealing 策略 — Medium [已对比] [P2 待修复]
- **Clef**: 按创建顺序（老化顺序）窃取 — 最老的优先被偷
- **addons/midi**: 按音量窃取 — 正在释放且音量最低 (`volume_db < -80dB`) 的优先被偷
- **影响**: addons/midi 的策略更符合心理声学（偷最安静的音符），听感更自然

### 7.3 Legato 快速释放 — ~~Critical~~ 已修复 [已对比] [已修复 959f6af]

**发现**: commit `2f0952b` 将 `start_note()` 从单 zone 重构为 multi-zone 循环时，**意外删除了 legato 快速释放逻辑**。

**旧版代码** (删除前):
```gdscript
# 单 zone 版 start_note() 中
for voice in _voices:
    if voice.channel == p_channel and not voice.is_idle() and voice.key != p_key:
        if voice.state != ClefVoice.State.ATTACK:
            voice.stop_note_legato()  # 30ms 极短 release
```

**新版代码** (2f0952b 后): 此段代码不存在。`start_note(inst_infos[])` 的 multi-zone 循环中只做了 retrigger（同 key）和 channel cap 检查，**完全跳过了同通道不同 key 的 legato 处理**。

**影响**:
- ~~小提琴连奏时，旧音符以正常 release (300ms+) 淡出，与新音符叠加产生"拍频/合唱"效果~~
- ~~快速连奏 (BPM=120, 16th notes) 时声音严重叠加浑浊~~
- ~~这是从单 zone 升级到 multi-zone 后听感退化的**直接原因**~~

**已修复 (commit 959f6af)**: 在 `clef_voice_pool.gd` 的 `start_note()` 中恢复了 legato 遍历，旧音符现在以 30ms 极短 release 快速淡出，跳过 ATTACK 状态的和弦不受影响。

---

## 8. 小提琴短音符连续变化专项分析

### 8.1 小提琴 SF2 Zone 结构

小提琴 (GM #40) 典型的 multi-zone 结构：
- **VlnStrike** (attack 层): 短促弓弦起音采样，non-looping，~200ms
- **Violin_1** (sustain 层): 持续振动采样，looping

两个插件的 zone 解析结果基本一致（commit `2f0952b` 修复后）。

### 8.2 短音符 Attack/Sustain 层交互 — 根因分析 [已对比] [已修复]

**场景**: 100ms 短音符 (staccato)，attack 层采样 ~200ms

**Clef 行为 (修复后)**:
1. note_on → 分配 2 个 voice (attack + sustain)，**每个 voice 音量补偿 /layer_count**
2. 当下一个音符进入时 → legato 快速释放前一个音符（**30ms** 而非 300ms）
3. attack 层和 sustain 层均以极短 release 淡出
4. **64 声部池** 确保快速连奏不会因声部不足被偷

**addons/midi 行为**:
1. note_on → 分配 2 个 ADSR voice (attack + sustain)
2. 100ms 后 note_off → 两个 voice 进入 release
3. 无 legato 快速释放（addons/midi 本身也没有 legato 机制）
4. 但由于 96 声部容量大，release 中的 voice 不会立即被偷

**根因 ~~及修复~~**: Legato 丢失（§7.3）是主因。**已通过 3 项修复解决**: legato 恢复 (P0) + 复音补偿 (P1) + 声部扩容 (P1)。

### 8.3 连续音高变化 (Portamento)

- **Clef**: 不支持 CC5/CC65/CC84，音高滑动仅依赖 pitch bend
- **addons/midi**: 部分支持（CC65 存储值但未实现实际滑音逻辑）
- **影响**: 两者均无真正可用的 portamento，差异不大

### 8.4 小提琴短音符差异的改进优先级

| 优先级 | 问题 | 影响 | 状态 |
|--------|------|------|------|
| **P0** | Legato 逻辑丢失 (§7.3) | 连奏浑浊 | ✅ [已修复 959f6af] |
| **P1** | 复音补偿缺失 (§5.5) | 双层叠加音量偏高 +6dB | ✅ [已修复 959f6af] |
| **P1** | 声部池过小 (§7.1) | 快速连奏偷声部 | ✅ [已修复 959f6af] |
| **P1** | Channel cap 过低 (§7.1) | 管弦乐丢音 | ✅ [已修复 959f6af] cap 8→16 |

---

## 9. 通用听感测试 [待听感验证]

> **需要在 Godot 中运行两个插件播放相同 MIDI 文件进行 A/B 对比测试**，验证代码修复的实际听感效果。

**重点验证项**:
1. ~~小提琴快速连奏 — staccato/spiccato/legato~~ → **P0 legato 修复后待验证**
2. ~~多声部叠加时音量平衡~~ → **P1 复音补偿修复后待验证**
3. ~~CC91/CC93 空间层次~~ → **P1 per-channel 效果器修复后待验证**
4. 钢琴独奏 — attack/decay 曲线、sustain pedal
5. 打击乐 — Channel 9 GM 鼓组
6. 持续音色 — loop 稳定性、vibrato
7. 高/低音域 — 大跨度 pitch_scale 音质
1. 钢琴独奏 — attack/decay 曲线、sustain pedal
2. 小提琴快速连奏 — staccato/spiccato/legato
3. 管弦乐合奏 — 多声部叠加、声部偷取
4. 打击乐 — Channel 9 GM 鼓组
5. 持续音色 — loop 稳定性、vibrato
6. 高/低音域 — 大跨度 pitch_scale 音质

---

## 10. 改进建议（按优先级排序）

### P0 — 必须修复 ✅ 全部已修复 (commit 959f6af)

#### ~~P0-1: 恢复 Legato 快速释放逻辑~~ ✅ 已修复
- **文件**: `addons/clef/player/clef_voice_pool.gd`
- **改动**: 在 `start_note()` 的 retrigger 检查后、multi-zone 循环前，恢复 legato 遍历
- **工作量**: 小（~5 行代码）

### P1 — 建议修复 ✅ 全部已修复 (commit 959f6af)

#### ~~P1-1: 添加 Multi-zone 复音补偿~~ ✅ 已修复
- **文件**: `addons/clef/player/clef_voice.gd` + `addons/clef/player/clef_voice_pool.gd`
- **改动**: `start_note()` 接受 `layer_count` 参数，`velocity_db -= linear_to_db(layer_count)`

#### ~~P1-2: 提升默认声部数~~ ✅ 已修复
- **文件**: `addons/clef/player/clef_voice_pool.gd`
- **改动**: `_max_voices` 32 → 64，channel cap 8 → 16

#### ~~P1-3: 添加 per-channel Reverb/Chorus 控制 (CC91/CC93)~~ ✅ 已修复
- **文件**: `addons/clef/player/midi_stream_player.gd`, `addons/clef/player/channel_state.gd`
- **改动**: Reverb/Chorus 从 ClefMaster 移到 per-channel 总线，CC91/CC93 控制 wet 值

### P2 — 可选改进

#### P2-1: 立体声声像子总线
- **文件**: `addons/clef/player/midi_stream_player.gd`
- **改动**: 每个通道添加 L/R 子总线，立体声采样分路由
- **工作量**: 中
- **风险**: 中

#### P2-2: Sustain Pedal 通过 ADSR 控制
- **文件**: `addons/clef/player/clef_voice.gd`
- **改动**: CC64 不直接调用 `stop_note()`，而是在 ADSR 中用 hold 标志阻止 release 状态转换
- **工作量**: 小
- **风险**: 低

#### P2-3: Decay 改为线性 dB 插值（与 addons/midi 对齐）
- **文件**: `addons/clef/player/clef_voice.gd`
- **改动**: DECAY 状态的插值从 `lerpf(1.0, db_to_linear(sustain_db), t)` 改为 `lerpf(0.0, sustain_db, t)`
- **工作量**: 小
- **风险**: 低（纯听感调整）

#### P2-4: Stealing 策略改为"最安静优先"
- **文件**: `addons/clef/player/clef_voice_pool.gd`
- **改动**: stealing 时优先选 `volume_db < -80` 的 releasing voice
- **工作量**: 小
- **风险**: 低

#### P2-5: 声部数和 Channel cap 暴露为 @export
- **文件**: `addons/clef/player/clef_voice_pool.gd`
- **改动**: `_max_voices` 和 channel cap 改为 `@export` 参数
- **工作量**: 小
- **风险**: 低

---

## 11. 附录：分析依据

### 代码文件清单

| 模块 | Clef | addons/midi |
|------|------|-------------|
| SF2 解析 | `sf2/sf2_reader.gd`, `sf2/sf2_bank.gd`, `sf2/sf2_data.gd` | `SoundFont.gd` |
| 音色库 | `player/clef_bank.gd` | `Bank.gd` |
| 音色单元 | `player/clef_voice.gd` | `ADSR.gd` |
| 声部池 | `player/clef_voice_pool.gd` | 内嵌于 `MidiPlayer.gd` |
| 通道状态 | `player/channel_state.gd` | 内嵌于 `MidiPlayer.gd` |
| 播放器 | `player/midi_stream_player.gd` | `MidiPlayer.gd` |
| 测试 | `tests/test_sf2_zones.gd`, `tests/test_sf2_inst314.gd` | — |

### 分析方法
- 逐文件代码审查 + 交叉对比
- 重点关注小提琴短音符场景（commit `2f0952b` 前后 diff）
- 数学公式验证（pitch、ADSR 插值、velocity 映射）
