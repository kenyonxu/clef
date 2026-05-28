# 小提琴短音符快速连奏：Clef vs addons/midi 行为差异分析

## 场景
小提琴 (GM #40) 短音符 (100-200ms) 快速连奏 (BPM 120, 16th notes = 125ms/note)
SF2 音色库：VlnStrike (attack 层, ~200ms 非循环) + Violin_1 (sustain 层, 循环)

---

## 发现 1: Multi-zone 版 start_note() 丢失 Legato 处理

- **现象**: 多 zone 版 `start_note(inst_infos[])` 完全没有 legato 快速释放逻辑，同通道前一个音符的所有 layer 都用 `stop_note()` (正常 release) 而非 `stop_note_legato()` (30ms 快速淡出)
- **Clef 行为**: `addons/clef/player/clef_voice_pool.gd` 多 zone 版 `start_note()` 只做了同通道同键位 `voice.stop_note()`，没有对同通道不同键位的活跃 voice 调用 `stop_note_legato()`。而单 zone 版有完整的 legato 逻辑（跳过 ATTACK 状态、30ms 快速淡出）
- **addons/midi 行为**: `addons/midi/MidiPlayer.gd` `_process_track_event_note_on()` 中，若 `channel.note_on.has(assign_group)` 则立即调用 `_process_track_event_note_off(channel, note, true)` 强制释放同键位旧音符。对同通道不同键位无特殊处理（依赖 voice pool 自然回收）
- **根因分析**: commit 2f0952b 添加 multi-zone layering 时，复制了 `start_note()` 但遗漏了 legato 部分。两个版本共存导致行为不一致
- **影响**: **Critical** — 短音符快速连奏时，前一个音符的 attack 层 (VlnStrike) 以正常 release (可能 300ms+) 淡出而非 30ms 快速淡出，导致声音叠加、浑浊
- **修复建议**: 在多 zone 版 `start_note(inst_infos[])` 的同键位停止之后、分配新 voice 之前，加入与单 zone 版一致的 legato 逻辑

---

## 发现 2: ADSR Release 插值方式差异

- **现象**: 两个插件的 ADSR release 阶段使用不同的 dB 插值策略
- **Clef 行为**: `addons/clef/player/clef_voice.gd` `_update_adsr()` RELEASE 阶段使用 **线性 dB 插值**: `lerpf(_release_start_db, -144.0, t)`。从当前音量到 -144dB 匀速下降，听觉上前期响、后期突然静音
- **addons/midi 行为**: `addons/midi/ADSR.gd` `_update_adsr()` release 阶段使用 `release_state` 预计算数组，从 `sustain_level` 到 `-144dB` 做 **线性 dB 插值**: `lerpf(pre_state.volume_db, state.volume_db, t)`。关键区别：release 从 `sustain_level` 开始，而非当前实际音量
- **根因分析**: Clef 的 release 从实际音量开始（更准确），但线性 dB 意味着前期音量变化慢、后期快。addons/midi 从固定 sustain_level 开始，虽然不够精确但行为一致可预测。两者都不是指数衰减（真实乐器行为）
- **影响**: **Medium** — 在短音符场景下差异不大（因为 release 被截断），但在中等长度音符上 Clef 的线性 dB release 听感更不自然
- **修复建议**: 长期可考虑改为指数衰减 `exp(-t/tau)` 匹配真实乐器；短期无需改动

---

## 发现 3: ADSR Attack/Decay 使用线性幅度 vs 线性 dB

- **现象**: 两个插件的 attack/decay 插值方式一致（线性幅度），但 addons/midi 有条件分支
- **Clef 行为**: `clef_voice.gd` ATTACK: `linear_to_db(lerpf(db_to_linear(-144.0), 1.0, t))` — 线性幅度插值。DECAY: `linear_to_db(lerpf(1.0, db_to_linear(_sustain_db), t))` — 线性幅度插值
- **addons/midi 行为**: `ADSR.gd` 对 state_number 1 和 2（即 attack 和 decay）使用线性幅度插值（与 Clef 一致），但 release 用线性 dB。注释明确写了 `if not self.releasing and all_states > 2 and (state_number == 1 or state_number == 2)`
- **根因分析**: 两者 attack/decay 行为一致。差异仅在 release
- **影响**: **Low** — attack/decay 行为一致，不是短音符问题的根因
- **修复建议**: 无需修改

---

## 发现 4: Polyphony Count 音量补偿

- **现象**: addons/midi 有 polyphony count 音量补偿，Clef 没有
- **Clef 行为**: 多 zone 同时发声时，每个 voice 独立以满音量播放。两个 layer (VlnStrike + Violin_1) 叠加后总音量约 +6dB
- **addons/midi 行为**: `ADSR.gd` `_update_volume()` 中 `v = linear_to_db(db_to_linear(v) / self.polyphony_count)`。当 `preset.instruments[key_number]` 有多个 instrument 匹配时，`polyphony_count` = 匹配数量，每个 voice 音量除以该数量。两个 layer 叠加后总音量与单 layer 一致
- **根因分析**: Clef 的 multi-zone 叠加没有做音量补偿，导致小提琴双 layer 发声时总音量偏高 +6dB。在快速连奏中，attack 层和 sustain 层叠加的音量突增可能被感知为"砰"的一声
- **影响**: **High** — 双层叠加时音量不一致，attack 层的弓弦噪声被放大
- **修复建议**: 在 `clef_voice_pool.gd` 的 multi-zone `start_note()` 中，计算匹配的 inst_infos 数量，将 `polyphony_count` 传递给每个 voice。在 `clef_voice.gd` 的 `_process()` 中除以该值

---

## 发现 5: Release 起始电平差异

- **现象**: addons/midi release 从固定的 sustain_level 开始，Clef 从当前实际音量开始
- **Clef 行为**: `_trigger_release()` 捕获 `volume_db - _velocity_db - _inst_volume_db` 作为 `_release_start_db`
- **addons/midi 行为**: 进入 releasing 时 `current_volume_db = release_state[0].volume_db`，即 SF2 中定义的 sustain level
- **根因分析**: 当短音符在 attack 阶段就被 note_off 时，Clef 会从 attack 中途的音量开始 release（正确），addons/midi 会跳到 sustain level 再 release（可能产生音量跳变）。反之，如果音符已进入 sustain，两者行为一致
- **影响**: **Low** — Clef 的行为更正确。addons/midi 在极短音符时可能有轻微音量跳变
- **修复建议**: 无需修改，Clef 行为更优

---

## 发现 6: Portamento / CC5 / CC65 / CC84 均不支持

- **现象**: 两个插件都不支持 portamento CC，但 addons/midi 有 portamento 状态变量
- **Clef 行为**: `addons/clef/player/channel_state.gd` 无 CC5/CC65/CC84 字段，无 portamento 概念
- **addons/midi 行为**: `addons/midi/MidiPlayer.gd` 的 `GodotMIDIPlayerChannelStatus` 有 `portamento: float` 和 `sostenuto: float` 变量，CC5 (portamento time) 和 CC65 (portamento on/off) 有处理入口，但 `portamento` 值仅存储、未用于实际音高滑变逻辑
- **根因分析**: 两个插件都未实现真正的 portamento。快速连奏的平滑感不依赖 portamento CC，而依赖 legato release 策略
- **影响**: **Low** — 不影响短音符问题，但限制了表现力
- **修复建议**: 长期可添加 portamento 支持（pitch bend 在 note_on 间平滑过渡）

---

## 发现 7: addons/midi note_on 对同键位强制释放

- **现象**: addons/midi 在 note_on 时若同键位已有音符，强制 `force_disable_hold=true` 立即释放
- **Clef 行为**: `stop_note()` 正常 release，若延音踏板开启则不释放 (`_sustained` 检查)
- **addons/midi 行为**: `_process_track_event_note_on()` 中 `if channel.note_on.has(assign_group): self._process_track_event_note_off(channel, note, true)` — `true` 表示 force_disable_hold，无论延音踏板状态都立即释放
- **根因分析**: addons/midi 的行为更激进——同键位重触发时无视延音踏板。Clef 尊重延音踏板。在正常无延音踏板的连奏场景下两者行为等价
- **影响**: **Low** — 仅在有延音踏板时有差异
- **修复建议**: 无需修改

---

## 关键发现总结

| # | 发现 | 影响 | 修复优先级 |
|---|------|------|-----------|
| 1 | Multi-zone start_note 丢失 legato | Critical | P0 |
| 4 | Multi-zone 无 polyphony 音量补偿 | High | P1 |
| 2 | Release 线性 dB vs 指数衰减 | Medium | P2 |
| 3 | Attack/Decay 插值一致 | Low | - |
| 5 | Release 起始电平差异 | Low | - |
| 6 | Portamento 不支持 | Low | P3 |
| 7 | 同键位释放策略差异 | Low | - |

**根本原因**: 发现 #1 (legato 丢失) + 发现 #4 (音量补偿缺失) 是导致短音符快速连奏听感差异的两个主要原因。Legato 丢失导致 attack 层长尾叠加，音量补偿缺失导致双 layer 音量突增。
