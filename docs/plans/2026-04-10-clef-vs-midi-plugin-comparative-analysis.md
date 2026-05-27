# Clef vs addons/midi 播放质量对比分析计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 系统性地对比 Clef 插件与 addons/midi 插件的 MIDI 播放链路，定位音色还原度差异的根本原因，输出一份完整的技术对比文档。

**Architecture:** 逐层拆解两个插件的 SF2 解析、采样制备、音高计算、ADSR 包络、通道状态管理、总线效果器、声部分配等模块，通过代码审查 + 听感测试 + MIDI 文件 A/B 对比的方法，找出所有影响播放质量的差异点。

**Tech Stack:** GDScript 代码审查、Godot 4.6 AudioServer、SF2 规范、音乐听感分析

---

## 前置知识：两个插件的核心架构差异

| 维度 | Clef (`addons/clef/`) | addons/midi (arlez80) |
|------|----------------------|----------------------|
| 音频后端 | `AudioStreamPlayer` + `pitch_scale` | `AudioStreamPlayer` + `pitch_scale`（相同） |
| 采样制备 | 按需提取，缓存 `AudioStreamWAV` | 加载时全量转换，含 125ms head silence |
| Multi-zone | ✅ 已支持（commit `2f0952b`），每音符多声部 | ✅ 全 zone 叠加，ADSR 预计算 |
| 音高计算 | `pow(2, base_pitch + key_offset + pb + mod)` | 相同公式，但 `base_pitch` 含采样率校正 |
| ADSR | 5 状态（A/H/D/S/R），attack 线性振幅，release 线性 dB | 3 状态（A/D/R），attack 线性振幅，release 线性 dB |
| 声部数 | 默认 32，含 legato 快速释放 | 默认 96（可扩至 256） |
| Legato | `stop_note_legato()` 极短 release | 无特殊 legato 处理，走正常 note_off |
| 总线架构 | 16 通道总线 + master | 16 通道总线 + 32 立体声子总线 + master |
| 效果器 | Reverb + Chorus + Panner（per-channel） | Chorus + Panner + Reverb（per-channel） |
| 滤波器 | 解析但未应用（bug 回避） | 无 |
| 采样去重 | 有缓存 key | 有更精细的 key（含采样率+基音） |

---

## 文件结构

**产出文件：**
- 创建: `docs/clef-vs-midi-comparative-analysis.md` — 最终对比分析报告

**审查文件（只读）：**

| 模块 | Clef 文件 | addons/midi 文件 |
|------|----------|-----------------|
| SF2 解析 | `addons/clef/sf2/sf2_reader.gd` | `addons/midi/SoundFont.gd` |
| 音色库/采样 | `addons/clef/sf2/sf2_bank.gd`, `addons/clef/player/clef_bank.gd` | `addons/midi/Bank.gd` |
| 音色单元 | `addons/clef/player/clef_voice.gd` | `addons/midi/ADSR.gd` |
| 声部池 | `addons/clef/player/clef_voice_pool.gd` | 内嵌于 `addons/midi/MidiPlayer.gd` |
| 通道状态 | `addons/clef/player/channel_state.gd` | 内嵌于 `addons/midi/MidiPlayer.gd` |
| 播放器 | `addons/clef/player/midi_stream_player.gd` | `addons/midi/MidiPlayer.gd` |
| MIDI 解析 | `addons/clef/midi_reader.gd` | `addons/midi/SMF.gd` |

---

## Task 1: SF2 采样制备对比

**目标：** 找出两个插件在从 SF2 文件提取 PCM 数据、生成 AudioStreamWAV 时的差异。

**Files:**
- 审查: `addons/clef/sf2/sf2_bank.gd` → `get_sample()` / `_compose_wav()`
- 审查: `addons/clef/player/clef_bank.gd` → `get_instrument()`
- 审查: `addons/midi/Bank.gd` → `_read_soundfont_preset_compose_sample()`

- [ ] **Step 1: 对比 SF2 Zone 解析逻辑**

审查以下差异点并记录到报告：
1. 全局 Zone（Global Zone）继承方式是否一致
2. Key Range / Velocity Range 匹配优先级
3. Generator 累积规则（Preset Zone + Instrument Zone 叠加）
4. 缺失 Generator 的默认值处理

预期输出：差异清单，标注哪些会导致音色选择错误。

- [ ] **Step 2: 对比采样切片与 AudioStreamWAV 生成**

逐一检查：
1. **Head silence**：Clef 的 `_HEAD_SILENT_SECOND` 值 vs addons/midi 的 125ms（5512 samples），是否影响播放时序
2. **采样率处理**：Clef 是否对非 44100Hz 采样做了采样率校正 pitch offset；addons/midi 通过 `log(sample_rate/44100)/log(2)` 加到 `base_pitch`
3. **Loop 处理**：loop_begin/loop_end 的计算方式是否一致（是否都考虑了 head silence 偏移）
4. **立体声分离**：Clef 是否将 L/R 分成独立 AudioStreamWAV；addons/midi 是的
5. **采样去重**：缓存 key 的构成差异

预期输出：每个差异点的影响评估（高/中/低）。

- [ ] **Step 3: 对比 multi-zone layering（多区域叠加）**

检查 SF2 同一 preset 下多个 instrument zone 匹配同一 key/velocity 时的处理：
1. Clef 是否叠加多个 zone 的采样（最近提交 `2f0952b` 应已支持）
2. addons/midi 如何处理 — 是否所有匹配 zone 都生成独立 AudioStreamWAV
3. 叠加时的音量补偿策略差异

预期输出：multi-zone 叠加行为的完整对比。

---

## Task 2: 音高计算与 Pitch Scale 对比

**目标：** 确认两个插件在 `pitch_scale` 计算上是否有精度差异。

**Files:**
- 审查: `addons/clef/player/clef_voice.gd` → `_update_adsr()` 中的 pitch 计算
- 审查: `addons/midi/ADSR.gd` → `_update_adsr()` 中的 pitch 计算

- [ ] **Step 1: 对比 base_pitch 来源与计算**

检查：
1. Clef 的 `base_pitch` 是从 `ClefInstrumentInfo` 获取，来源是 `sf2_bank.gd` 的解析 — 确认它是否包含采样率校正
2. addons/midi 的 `base_pitch` 包含：`coarse_tune/12 + fine_tune/1200 + pitch_correction/1200 + log(sample_rate/44100)/log(2)`
3. key_offset 计算：`(note_key - root_key) / 12.0` 两者是否一致

预期输出：`base_pitch` 组成分项对比表。

- [ ] **Step 2: 对比弯音（Pitch Bend）计算**

检查：
1. Clef: `pitch_bend * pitch_bend_sensitivity / 12.0`（pitch_bend 范围 -1..+1）
2. addons/midi: `pitch_bend * pitch_bend_sensitivity / 12.0`（pitch_bend 范围 0..1）
3. 14-bit pitch bend 值的归一化方式差异
4. pitch_bend_sensitivity 默认值是否一致（都是 2 semitones?）

预期输出：弯音计算公式对比，标注归一化差异。

- [ ] **Step 3: 对比颤音（Modulation / Vibrato）**

检查：
1. LFO 频率：Clef 用 `sin(t * 32.0)` ≈ 5.09Hz，addons/midi 用 `sin(using_timer * 32.0)` ≈ 5.09Hz
2. 深度计算是否一致
3. CC1 (Modulation Wheel) 的灵敏度默认值
4. RPN 数据入口（Data Entry）的处理是否一致

预期输出：颤音参数完整对比。

---

## Task 3: ADSR 包络对比

**目标：** 找出包络形状差异，这直接影响音色的起音和释放听感。

**Files:**
- 审查: `addons/clef/player/clef_voice.gd` → ADSR 状态机
- 审查: `addons/midi/ADSR.gd` → ADSR 状态机

- [ ] **Step 1: 对比 Attack 阶段**

检查：
1. Clef: 线性振幅插值 `linear_to_db(lerpf(db_to_linear(-144), 1.0, t))`
2. addons/midi: 线性振幅插值 `linear_to_db(lerpf(db_to_linear(prev_db), db_to_linear(next_db), t))`
3. Attack 时长来源：SF2 的 `attack_volenv` generator
4. Hold 阶段：Clef 有独立的 Hold 状态，addons/midi 是否也有

预期输出：Attack 曲线数学公式对比。

- [ ] **Step 2: 对比 Decay 和 Sustain 阶段**

检查：
1. Decay 插值方式（线性振幅 vs 线性 dB）
2. Sustain level 来源（SF2 `sustain_volenv`，单位是 0.1dB 衰减量）
3. Sustain dB 到线性值的转换是否一致

预期输出：Decay+Sustain 参数处理对比。

- [ ] **Step 3: 对比 Release 阶段与防咔嗒声机制**

检查：
1. Release 插值方式差异（都是线性 dB？）
2. Release 时长来源
3. **Mix latency 补偿**：Clef 的 `_request_release_second` vs addons/midi 的 `gap_second - AudioServer.get_time_to_next_mix()`
4. Non-looping 采样的自动释放策略

预期输出：Release 处理对比，这是音质差异的关键点之一。

- [ ] **Step 4: 对比 Velocity 到音量的映射**

检查：
1. Clef: `linear_to_db(velocity / 127.0)`
2. addons/midi: `current_volume_db + linear_to_db(velocity / 127.0)`
3. **复音补偿**：addons/midi 有 `polyphony_count` 除法，Clef 是否有类似机制
4. SF2 initial_attenuation generator 的应用方式

预期输出：Velocity 曲线对比，标注复音叠加时的音量差异。

---

## Task 4: 通道状态与效果器对比

**目标：** 对比 CC 处理、总线效果器架构对最终听感的影响。

**Files:**
- 审查: `addons/clef/player/channel_state.gd`
- 审查: `addons/clef/player/midi_stream_player.gd` → `_setup_clef_bus()`
- 审查: `addons/midi/MidiPlayer.gd` → `_setup_bus()` / channel status

- [ ] **Step 1: 对比 CC 处理范围**

检查以下 CC 的支持情况：

| CC | 功能 | Clef | addons/midi |
|----|------|------|-------------|
| CC1 | Modulation | ? | ? |
| CC7 | Volume | ? | ? |
| CC10 | Pan | ? | ? |
| CC11 | Expression | ? | ? |
| CC64 | Sustain | ? | ? |
| CC91 | Reverb | ? | ? |
| CC93 | Chorus | ? | ? |

标注每个 CC 的应用方式差异（如 Clef 用 bus volume vs addons/midi 用 AudioEffect 参数）。

- [ ] **Step 2: 对比总线效果器架构**

检查：
1. 效果器挂载顺序差异
2. Reverb 参数（room_size、damping、wet、dry）的默认值
3. Chorus 参数差异
4. Panner 实现（AudioEffectPanner vs bus panning）
5. 是否有 Compressor / EQ 等 Clef 缺失的效果器

预期输出：效果器链路图对比。

- [ ] **Step 3: 对比 Pan（声像）实现**

检查：
1. Clef: 是否用 `AudioEffectPanner` per-channel bus
2. addons/midi: 用 `AudioEffectPanner` per-channel bus + 立体声子总线的硬声像
3. 立体声采样的声像处理差异
4. CC10 值到 pan 参数的映射公式

预期输出：声像实现方式对比。

---

## Task 5: 声部分配与资源管理对比

**目标：** 对比声部池管理策略，找出复音冲突时的差异。

**Files:**
- 审查: `addons/clef/player/clef_voice_pool.gd` → `start_note()` / `_find_voice()`
- 审查: `addons/midi/MidiPlayer.gd` → `_get_idle_player()`

- [ ] **Step 1: 对比声部分配策略**

检查：
1. 预分配数量：Clef 32 vs addons/midi 96
2. 分配优先级顺序
3. Stealing 策略差异（Clef: channel cap → idle → oldest releasing → oldest active; addons/midi: idle → quietest releasing → oldest active）
4. 同 key retrigger 处理
5. Legato 处理（Clef 有专门的 legato 快速释放）

预期输出：声部分配流程图对比。

- [ ] **Step 2: 对比声部数对听感的影响**

分析：
1. 32 vs 96 声部在复杂编曲（如管弦乐）中是否会因声部不足导致音符被偷
2. Channel cap（Clef 的 8 声部/通道限制）是否过于激进
3. 声部不足时的替代策略对听感的实际影响

预期输出：声部数需求的量化评估。

---

## Task 6: 【重点】小提琴短音符连续变化深度对比

**目标：** 深入分析小提琴在快速连奏（staccato/spiccato）和音高连续变化（portamento）场景下，两个插件的播放差异。这是当前最突出的音质问题。

**背景：** commit `2f0952b` 已修复 multi-zone layering（VlnStrike attack 层 + Violin_1 sustain 层同时触发），小提琴基本可正常播放。但在短音符快速连续变化时，听感仍不如 addons/midi。

**Files:**
- 审查: `addons/clef/player/clef_voice_pool.gd` → `start_note()` 中的 legato / 同通道处理
- 审查: `addons/clef/player/clef_voice.gd` → `stop_note_legato()` / ADSR 状态机 / `_request_release_second`
- 审查: `addons/clef/player/sf2_bank.gd` → `get_samples()` 多 zone 匹配逻辑
- 审查: `addons/clef/player/midi_stream_player.gd` → `_process_event()` note_on/note_off 处理
- 审查: `addons/midi/MidiPlayer.gd` → `_get_idle_player()` / `_note_on()` / `_note_off()`
- 审查: `addons/midi/ADSR.gd` → release 机制 / 多 layer 处理
- 审查: `addons/midi/Bank.gd` → violin preset 的 zone 分解和 ADSR 预计算
- 参考: `addons/clef/tests/test_sf2_zones.gd` — 已有的小提琴 zone 测试

- [ ] **Step 1: 对比小提琴 SF2 Zone 结构解析**

小提琴 preset (GM #40) 通常包含多个 zone：
1. **VlnStrike**（attack 层）：短促的弓弦起音采样，通常为 non-looping
2. **Violin_1**（sustain 层）：持续振动采样，通常为 looping
3. 可能还有按 velocity 或 key range 细分的 zone

逐一检查：
1. 两个插件对小提琴 preset 解析出的 zone 数量和内容是否一致
2. 每个 zone 的 key_range、vel_range、sample、loop 设置
3. Attack 层采样长度和 non-looping 标记是否正确传递
4. Sustain 层 loop 点是否精确匹配

**方法：** 编写诊断脚本或在 Godot 中运行 `test_sf2_zones.gd`，打印 Clef 解析出的小提琴 zone 详情，对比 addons/midi 的 `Bank._read_soundfont_preset_compose_sample()` 处理相同 preset 的结果。

预期输出：两个插件的 zone-by-zone 对比表。

- [ ] **Step 2: 对比短音符时 Attack 层与 Sustain 层的交互**

这是小提琴短音符差异的核心。快速连奏时：

1. **Attack 层时长**：VlnStrike 采样实际有多长？如果 attack 层是 200ms 采样，但音符只持续 100ms，两个插件如何处理？
   - Clef: note_off 触发后是否立即释放 attack 层？还是等待 attack 层自然结束？
   - addons/midi: 同场景的处理方式
2. **Sustain 层在短音符中的角色**：如果音符在 attack 到达 sustain 之前就结束，sustain 层的 looping 采样是否还被触发？对音质有何影响？
3. **双倍声部消耗**：multi-zone layering 意味着每个音符消耗 2 个声部。连续 16 个短音符 = 32 个声部（16 attack + 16 release 中的 sustain），是否触发 Clef 的 32 声部上限？
4. **Release 重叠**：短音符 A 的 release 尾音与短音符 B 的 attack 叠加时，两个插件的音量叠加效果是否一致？

预期输出：短音符生命周期时序图（Clef vs addons/midi），标注 attack/sustain/release 层的起止时间。

- [ ] **Step 3: 对比 Legato/同通道快速连奏处理**

小提琴连奏时，前后音符同通道、时间紧密衔接：

1. **Clef 的 `stop_note_legato()`**：
   - 触发条件：同通道不同 key 的非 ATTACK 状态声部
   - 释放方式：极短 release（固定值？还是用 zone 的 release？）
   - 对 multi-zone 的影响：legato 是否同时快速释放 attack 层和 sustain 层？
   - 问题猜测：legato 快速释放可能导致 attack 层被截断过快，丢失弓弦起音特征

2. **addons/midi 的同通道处理**：
   - 是否有类似的 legato 快速释放机制？
   - 还是用正常的 note_off → release 流程？
   - 同 key retrigger 时（同音连奏）如何处理？

3. **Channel cap 交互**：Clef 的 8 声部/通道限制 + legato 策略 + multi-zone（每音 2 声部）= 同通道最多同时 4 个音符在发声（含 release），这是否足够？

预期输出：快速连奏（BPM=120, 16th notes）时两个插件的声部分配和释放时序对比。

- [ ] **Step 4: 对比连续音高变化（Portamento/Glissando）处理**

检查两个插件对弯音在音符间连续变化的支持：

1. **Pitch bend 刷新频率**：Clef 在 `_process()` 中每帧更新所有活跃声部的 `pitch_scale`，addons/midi 同样在 `_process()` 中更新。两者是否有帧率差异？
2. **跨音符 pitch bend**：如果 MIDI 数据中 pitch bend 事件在 note_off 和下一个 note_on 之间变化，两个插件是否都能正确保留 bend 值？
3. **Portamento CC (CC5/CC65/CC84)**：
   - Clef 是否支持 CC5（Portamento Time）、CC65（Portamento On/Off）、CC84（Portamento Control）？
   - addons/midi 是否支持？
   - 如果不支持，弯音是唯一的音高滑动手段，这是否是短音符连续变化的听感差异原因？

预期输出：pitch 连续变化机制的完整对比。

- [ ] **Step 5: 对比短音符的 ADSR 时间参数**

小提琴短音符的 ADSR 参数对听感极为敏感：

1. **Attack 时间**：SF2 中 VlnStrike zone 的 `attack_volenv` 值是多少？两个插件是否都正确读取并应用？
2. **Hold 时间**：`hold_volenv` 是否被 Clef 正确处理？addons/midi 是否有 Hold 阶段？
3. **Decay 时间**：短音符可能在 decay 未完成时就 note_off，两个插件的 decay → release 切换行为是否一致？
4. **Release 时间**：短音符的 release 尾音是否过长，导致与下一个音符的 attack 重叠过多？
5. **Attack 层 vs Sustain 层的 ADSR 参数差异**：两个 zone 可能有完全不同的 ADSR 设置，是否都正确应用？

**方法：** 在 Godot 中打印小提琴各 zone 的 ADSR 参数值（attack/hold/decay/sustain/release），逐一对比。

预期输出：ADSR 参数分 zone 对比表。

- [ ] **Step 6: 专项听感测试 — 小提琴快速段落**

制作或选取一段小提琴快速测试 MIDI：

1. **Staccato 测试**：C4 音符，时长 1/16（BPM=120，约 125ms），连续 8 个音
2. **Spiccato 测试**：交替 C4-D4，时长 1/16，连续 16 个音
3. **Portamento 测试**：C4→D4 滑音（通过 pitch bend 或连续 CC），时长 1/4
4. **Legato 弓弦测试**：C4→D4→E4→F4，各 1/8，无间隙（note_off 和 note_on 几乎同时）
5. **Velocity 变化测试**：同一音高，velocity 从 30→120 递增的 8 个短音符

每个测试在两个插件中播放，记录：
- 起音清晰度（是否有"黏糊"感）
- 音符间分隔度（是否听起来像连续的噪音而非独立音符）
- Attack 层的存在感（短音符是否能听到弓弦起音）
- Release 尾音是否干扰下一个音符
- 音高变化是否平滑

预期输出：5 个测试场景的 A/B 听感记录表。

---

## Task 7: 通用听感 A/B 测试

**目标：** 用具体 MIDI 文件做 A/B 对比，记录可感知的音质差异（小提琴专项测试已在 Task 6 中完成）。

**Files:**
- 准备: 测试用 MIDI 文件（至少覆盖 3 种场景）
- 运行: Godot 编辑器中分别用两个插件播放

- [ ] **Step 1: 准备测试 MIDI 文件**

准备以下测试场景的 MIDI（小提琴已在 Task 6 中专项覆盖）：
1. **钢琴独奏** — 测试 attack 灵敏度、sustain pedal、release 尾音
2. **管弦乐合奏** — 测试多声部叠加、声部偷取、复音补偿
3. **打击乐** — 测试 Channel 9 GM 鼓组
4. **持续音色（弦乐/Pad）** — 测试 loop 采样、sustain 阶段稳定性、modulation/vibrato
5. **高音域/低音域** — 测试大跨度 pitch_scale 的音质（非线性失真）
6. **其他多 zone 乐器**（如 Cello、Flute）— 验证 multi-zone layering 是否在其他乐器上也存在差异

- [ ] **Step 2: 在 Godot 中运行 A/B 测试**

对每个测试场景：
1. 用 addons/midi 的 MidiPlayer 播放，记录听感
2. 用 Clef 的 MidiStreamPlayer 播放同一 MIDI，记录听感
3. 标注差异：音色选择是否正确、起音是否自然、释放是否有咔嗒声、音量平衡、声像定位

- [ ] **Step 3: 整理听感差异清单**

按严重程度分类：
- **Critical**: 明显的音频故障（咔嗒声、爆音、错音）
- **High**: 音色还原度明显偏差（听得出不是同一个乐器）
- **Medium**: 音质差异需要仔细对比才能发现
- **Low**: 微妙差异，仅在专业监听环境下可察觉

---

## Task 8: 撰写最终对比分析报告

**目标：** 将所有发现整合为一份结构化的技术文档。

**Files:**
- 创建: `docs/clef-vs-midi-comparative-analysis.md`

- [ ] **Step 1: 撰写报告框架**

报告结构：
```markdown
# Clef vs addons/midi 播放质量对比分析

## 1. 概述
## 2. 架构对比总览
## 3. SF2 采样制备差异
## 4. 音高计算差异
## 5. ADSR 包络差异
## 6. 通道状态与效果器差异
## 7. 声部分配差异
## 8. 小提琴短音符连续变化专项分析
## 9. 通用听感测试结果
## 10. 改进建议（按优先级排序）
## 11. 附录：测试用 MIDI 文件清单
```

- [ ] **Step 2: 填充各章节内容**

将 Task 1-7 的发现填入对应章节，每个差异点包含：
- **现象描述**：具体差异是什么
- **代码定位**：两个插件中对应的文件和函数
- **根因分析**：为什么会产生差异
- **影响评估**：对听感的影响程度（Critical/High/Medium/Low）
- **修复建议**：如果要在 Clef 中改进，具体改什么

- [ ] **Step 3: 撰写改进建议（按优先级排序）**

根据所有发现的汇总，给出 Clef 改进的优先级建议：
1. **P0 — 必须修复**：导致音频故障或严重音色偏差的问题
2. **P1 — 建议修复**：明显可察觉的音质差异
3. **P2 — 可选改进**：细微差异或边缘场景

每个建议包含：改动文件、改动内容、工作量估算（小/中/大）、风险等级。

- [ ] **Step 4: 提交文档**

```bash
git add docs/clef-vs-midi-comparative-analysis.md
git commit -m "docs: add Clef vs addons/midi playback quality comparative analysis"
```

---

## 预期关键发现（基于代码审查的初步判断）

根据代码审查，以下差异最可能影响听感：

### 通用差异
1. **采样率校正缺失**（High）— 如果 Clef 未对非 44100Hz 采样做 pitch offset 校正，这些采样会偏高或偏低
2. **复音补偿缺失**（Medium）— addons/midi 有 polyphony_count 除法防削波，Clef 没有
3. **声部数不足**（Medium-High）— 32 vs 96，复杂编曲中 Clef 可能频繁偷声部
4. **立体声处理差异**（Medium）— addons/midi 有独立的 L/R 子总线，Clef 可能混为单声道或用简单 panner
5. **效果器参数默认值**（Low-Medium）— Reverb/Chorus 的默认参数可能不同
6. **Channel cap 过于激进**（Medium）— Clef 的 8 声部/通道限制可能导致某些乐器声部被意外偷走

### 小提琴短音符差异（重点关注）
7. **Attack 层被 legato 快速截断**（High）— Clef 的 `stop_note_legato()` 可能过早终止 VlnStrike attack 层，丢失弓弦起音特征
8. **Multi-zone 双倍声部消耗**（High）— 每个音符 2 声部 + 32 声部上限 = 快速连奏时极易触顶
9. **短音符 ADSR 交互**（Medium-High）— attack 层和 sustain 层在短音符下的 ADSR 叠加行为可能与 addons/midi 不同
10. **Portamento/滑音缺失**（Medium）— 如果 Clef 不支持 CC5/CC65/CC84，弦乐的连续音高变化只能靠 pitch bend，表现力受限
