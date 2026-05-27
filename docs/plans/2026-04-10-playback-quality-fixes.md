# Clef 播放质量系统性修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复对比分析中发现的 P0/P1 级音质差异，显著改善小提琴短音符连奏听感。

**Architecture:** 从对比分析报告 (`docs/clef-vs-midi-comparative-analysis.md`) 中提取的 4 项修复，按优先级排序：legato 恢复 → 复音补偿 → 声部扩容 → CC91/CC93 支持。每项修复独立提交，可单独验证。

**Tech Stack:** GDScript、Godot 4.6 AudioServer、SF2 合成

---

## File Structure

| 文件 | Task | 改动 |
|------|-------|------|
| `addons/clef/player/clef_voice_pool.gd` | 1, 2, 3 | 恢复 legato + 复音补偿传参 + 扩容 |
| `addons/clef/player/clef_voice.gd` | 2 | 接收 layer_count 做音量补偿 |
| `addons/clef/player/channel_state.gd` | 4 | 新增 reverb/chorus 字段 |
| `addons/clef/player/midi_stream_player.gd` | 4 | per-channel 效果器 + CC91/93 处理 |
| `addons/clef/tests/test_voice_pool.gd` | 1, 2 | 新建：legato 和复音补偿测试 |

---

### Task 1: 恢复 Legato 快速释放逻辑 (P0)

**Files:**
- Modify: `addons/clef/player/clef_voice_pool.gd:25-28`

**背景:** commit `2f0952b` 将 `start_note()` 从单 zone 重构为 multi-zone 循环时，删除了同通道不同音高的 legato 快速释放遍历。旧音以正常 release (300ms+) 淡出，与小提琴快速连奏的新音叠加产生浑浊。

- [ ] **Step 1: 在 `start_note()` 中恢复 legato 逻辑**

在 `clef_voice_pool.gd` 的 `start_note()` 方法中，将当前第 22-24 行的同 key retrigger 检查之后（`voice.stop_note()` 循环之后）、`for inst_info in inst_infos:` 循环之前（第 28 行之前），插入以下代码：

```gdscript
	# Legato: 同通道不同音高的活跃音符快速释放
	# 跳过 ATTACK 状态防止和弦音符互相触发 legato
	for voice in _voices:
		if voice.channel == p_channel and not voice.is_idle() and voice.key != p_key:
			if voice.state != ClefVoice.State.ATTACK:
				voice.stop_note_legato()
```

完整的 `start_note()` 方法头部应变为：
```gdscript
func start_note(p_channel: int, p_key: int, velocity: int,
		inst_infos: Array[ClefInstrumentInfo], rel_mult: float = 1.0) -> ClefVoice:
	# 同通道同键位的活跃音符先停止
	for voice in _voices:
		if voice.channel == p_channel and voice.key == p_key and not voice.is_idle():
			voice.stop_note()

	# Legato: 同通道不同音高的活跃音符快速释放
	for voice in _voices:
		if voice.channel == p_channel and not voice.is_idle() and voice.key != p_key:
			if voice.state != ClefVoice.State.ATTACK:
				voice.stop_note_legato()

	var first_voice: ClefVoice = null

	for inst_info in inst_infos:
		# ... (后续不变)
```

- [ ] **Step 2: 在 Godot 中验证修复**

1. 在 Godot 编辑器中打开项目
2. 用 Clef 的 MidiStreamPlayer 播放一段小提琴快速连奏 MIDI（BPM=120, 16th notes）
3. 确认：连奏时旧音符快速淡出（~30ms），不再与新音符叠加产生浑浊
4. 确认：和弦（多个 note_on 在同一 tick）不受影响，因为 ATTACK 状态的 voice 被跳过

- [ ] **Step 3: Commit**

```bash
git add addons/clef/player/clef_voice_pool.gd
git commit -m "fix(clef): restore legato fast release in multi-zone start_note()

Commit 2f0952b accidentally removed the legato traversal when
refactoring start_note() to multi-zone. Old notes on the same channel
with different keys were no longer fast-released (30ms), causing muddy
overlap during fast violin passages."
```

---

### Task 2: 添加 Multi-zone 复音补偿 (P1)

**Files:**
- Modify: `addons/clef/player/clef_voice_pool.gd:42` (start_note 内层循环)
- Modify: `addons/clef/player/clef_voice.gd:94-116` (start_note 方法签名 + 音量计算)

**背景:** addons/midi 在 `ADSR._update_volume()` 中用 `polyphony_count` 做音量除法补偿。Clef 没有。2 层叠加时总音量偏高约 +6dB，导致小提琴 attack 层弓弦噪声被放大。

- [ ] **Step 1: 修改 ClefVoice.start_note() 接受 layer_count 参数**

在 `clef_voice.gd` 第 94 行，修改方法签名，增加 `layer_count: int = 1` 参数：

```gdscript
## 启动音符
func start_note(inst_info: ClefInstrumentInfo, p_channel: int, p_key: int,
		velocity: int, rel_mult: float = 1.0, layer_count: int = 1) -> void:
```

在第 116 行（`_velocity_db` 赋值）之后，添加复音补偿：

```gdscript
	# 力度
	_velocity_db = linear_to_db(float(velocity) / 127.0)

	# Multi-zone 复音补偿: N 层叠加时每层降低 N 倍，防止削波
	if layer_count > 1:
		_velocity_db -= linear_to_db(float(layer_count))
```

- [ ] **Step 2: 在 ClefVoicePool.start_note() 中传入 layer_count**

在 `clef_voice_pool.gd` 的 `start_note()` 方法中，在 `for inst_info in inst_infos:` 循环之前，计算 layer 数量并传入每次 `start_note` 调用。

在第 28 行 (`for inst_info in inst_infos:`) 之前插入：

```gdscript
	var layer_count: int = inst_infos.size()
```

修改循环内的 `found.start_note(...)` 调用（共 3 处，约第 42、52、62 行），添加 `layer_count` 参数：

第 42 行附近：
```gdscript
			found.start_note(inst_info, p_channel, p_key, velocity, rel_mult, layer_count)
```

第 52 行附近：
```gdscript
			found.start_note(inst_info, p_channel, p_key, velocity, rel_mult, layer_count)
```

第 62 行附近：
```gdscript
			found.start_note(inst_info, p_channel, p_key, velocity, rel_mult, layer_count)
```

- [ ] **Step 3: 在 Godot 中验证**

1. 播放一段小提琴 MIDI，对比修复前后的音量
2. 确认：小提琴音量不再比其他乐器（如钢琴，单 zone）明显偏大
3. 确认：2 层叠加的总音量与单层音量基本一致（±1dB）
4. 确认：单 zone 乐器（layer_count=1）不受影响

- [ ] **Step 4: Commit**

```bash
git add addons/clef/player/clef_voice_pool.gd addons/clef/player/clef_voice.gd
git commit -m "fix(clef): add multi-zone polyphony compensation

When N zones layer together (e.g. violin VlnStrike + Violin_1), each
layer's velocity_db is reduced by linear_to_db(N) to maintain consistent
per-note volume. Matches addons/midi's polyphony_count behavior."
```

---

### Task 3: 提升默认声部数与 Channel Cap (P1)

**Files:**
- Modify: `addons/clef/player/clef_voice_pool.gd:7,36`

**背景:** 32 声部 + 8/通道 cap 在 multi-zone 下严重不足。2 zone 乐器 × 8 cap = 每通道最多 4 音符，管弦乐必然丢音。addons/midi 默认 96 声部且无 per-channel 限制。

- [ ] **Step 1: 修改默认值**

在 `clef_voice_pool.gd` 第 7 行，将默认值从 32 改为 64：

```gdscript
var _max_voices: int = 64
```

修改第 9 行的默认参数：

```gdscript
func _init(parent: Node, max_voices: int = 64) -> void:
```

在第 36 行，将 channel cap 从 8 改为 16：

```gdscript
			if channel_active >= 16:
```

- [ ] **Step 2: 在 Godot 中验证**

1. 播放一段管弦乐合奏 MIDI（多通道同时发声）
2. 确认：不再出现 `[STEAL_ACTIVE]` 或 `[STEAL_RELEASING]` 警告（除非极端密集）
3. 确认：小提琴快速连奏不再因声部不足丢音
4. 确认：内存占用合理（64 个 AudioStreamPlayer 节点）

- [ ] **Step 3: Commit**

```bash
git add addons/clef/player/clef_voice_pool.gd
git commit -m "fix(clef): increase default voice pool to 64 and channel cap to 16

32 voices with 8/channel cap was insufficient for multi-zone instruments.
2-zone violin × 8 cap = max 4 simultaneous notes per channel, causing
dropped notes in orchestral passages. 64 voices / 16 per-channel matches
addons/midi's 96-voice behavior for most practical scenarios."
```

---

### Task 4: 添加 Per-channel Reverb/Chorus 控制 (CC91/CC93) (P1)

**Files:**
- Modify: `addons/clef/player/channel_state.gd` — 新增 reverb/chorus 字段
- Modify: `addons/clef/player/midi_stream_player.gd` — 总线效果器重构 + CC 处理

**背景:** addons/midi 在每个通道总线上挂独立的 Reverb/Chorus 效果器，通过 CC91/CC93 控制 wet 值。Clef 的 Reverb/Chorus 挂在全局 ClefMaster 总线上，无法 per-channel 控制，导致无法实现"钢琴近场+弦乐远场"等空间层次。

- [ ] **Step 1: 在 MidiChannelState 中添加 reverb 和 chorus 字段**

在 `channel_state.gd` 第 13 行（`modulation`）之后添加：

```gdscript
## CC91: Reverb Send (归一化 0.0-1.0, 默认 0)
var reverb: float = 0.0
## CC93: Chorus Send (归一化 0.0-1.0, 默认 0)
var chorus: float = 0.0
```

在 `reset()` 方法中（第 36 行 `modulation = 0.0` 之后）添加：

```gdscript
	reverb = 0.0
	chorus = 0.0
```

- [ ] **Step 2: 在 midi_stream_player.gd 中将 Reverb/Chorus 移到 per-channel 总线**

修改 `_setup_audio_buses()` 方法。将 Reverb 和 Chorus 从 ClefMaster 总线移到每个通道子总线。

删除 ClefMaster 上的 Reverb/Chorus 创建代码（约第 308-330 行的 `has_reverb`/`has_chorus` 块）。

修改通道子总线创建循环（约第 332-343 行），在每个通道总线上添加 Panner + Reverb + Chorus：

```gdscript
	# 为每个通道创建子总线（含 Panner + Reverb + Chorus）
	for i in range(16):
		var ch_name := "clef_ch_%d" % i
		var ch_idx := AudioServer.get_bus_index(ch_name)
		if ch_idx < 0:
			AudioServer.add_bus(-1)
			ch_idx = AudioServer.get_bus_count() - 1
			AudioServer.set_bus_name(ch_idx, ch_name)
			AudioServer.set_bus_send(ch_idx, "ClefMaster")
			AudioServer.set_bus_volume_db(ch_idx, 0.0)
		# 确保效果器存在
		var has_panner := false
		var has_reverb := false
		var has_chorus := false
		for k in range(AudioServer.get_bus_effect_count(ch_idx)):
			var fx = AudioServer.get_bus_effect(ch_idx, k)
			if fx is AudioEffectPanner:
				has_panner = true
			elif fx is AudioEffectReverb:
				has_reverb = true
			elif fx is AudioEffectChorus:
				has_chorus = true
		if not has_panner:
			var panner := AudioEffectPanner.new()
			panner.pan = 0.0
			AudioServer.add_bus_effect(ch_idx, panner)
		if not has_reverb:
			var reverb := AudioEffectReverb.new()
			reverb.predelay_msec = 15.0
			reverb.room_size = reverb_room_size
			reverb.damping = 0.3
			reverb.hipass = 0.05
			reverb.wet = 0.0  # 初始关闭，由 CC91 控制
			AudioServer.add_bus_effect(ch_idx, reverb)
		if not has_chorus:
			var chorus := AudioEffectChorus.new()
			chorus.wet = 0.0  # 初始关闭，由 CC93 控制
			AudioServer.add_bus_effect(ch_idx, chorus)
```

- [ ] **Step 3: 在 _process_cc() 中添加 CC91 和 CC93 处理**

在 `midi_stream_player.gd` 的 `_process_cc()` 方法的 match 语句中（约第 740 行 CC64 之后），添加：

```gdscript
			91:  # Reverb Send
				state.reverb = float(value) / 127.0
				_apply_channel_reverb(ch)
			93:  # Chorus Send
				state.chorus = float(value) / 127.0
				_apply_channel_chorus(ch)
```

- [ ] **Step 4: 添加 _apply_channel_reverb() 和 _apply_channel_chorus() 方法**

在 `midi_stream_player.gd` 的 `_apply_channel_pan()` 方法之后（约第 812 行之后），添加：

```gdscript
## 应用通道混响深度 (CC91)
func _apply_channel_reverb(ch: int) -> void:
	var state: MidiChannelState = _channel_states[ch]
	var bus_idx: int = AudioServer.get_bus_index("clef_ch_%d" % ch)
	if bus_idx < 0:
		return
	for i in range(AudioServer.get_bus_effect_count(bus_idx)):
		var effect = AudioServer.get_bus_effect(bus_idx, i)
		if effect is AudioEffectReverb:
			effect.wet = state.reverb * reverb_wet
			break


## 应用通道合唱深度 (CC93)
func _apply_channel_chorus(ch: int) -> void:
	var state: MidiChannelState = _channel_states[ch]
	var bus_idx: int = AudioServer.get_bus_index("clef_ch_%d" % ch)
	if bus_idx < 0:
		return
	for i in range(AudioServer.get_bus_effect_count(bus_idx)):
		var effect = AudioServer.get_bus_effect(bus_idx, i)
		if effect is AudioEffectChorus:
			effect.wet = state.chorus * chorus_wet
			break
```

注意：`reverb_wet` 和 `chorus_wet` 已是 MidiStreamPlayer 的现有 `@export` 变量（用作全局最大值），这里用 `state.reverb * reverb_wet` 作为 per-channel 的实际 wet 值。

- [ ] **Step 5: 更新 reset() 和 stop() 中的效果器重置**

在 `stop()` 方法中（约第 376 行 `for i in range(16):` 循环内），在 `_apply_channel_volume(i)` 之后添加：

```gdscript
		_apply_channel_reverb(i)
		_apply_channel_chorus(i)
```

- [ ] **Step 6: 在 Godot 中验证**

1. 播放一段包含 CC91/CC93 的 MIDI 文件
2. 确认：CC91=0 的通道无混响，CC91=127 的通道混响最强
3. 确认：各通道的混响/合唱深度独立可控
4. 确认：不发送 CC91/CC93 时，默认无混响/合唱（wet=0）
5. 确认：ClefMaster 上的 Compressor/EQ 仍然正常工作

- [ ] **Step 7: Commit**

```bash
git add addons/clef/player/channel_state.gd addons/clef/player/midi_stream_player.gd
git commit -m "feat(clef): add per-channel Reverb/Chorus control (CC91/CC93)

Move Reverb and Chorus effects from global ClefMaster bus to per-channel
buses, enabling independent spatial depth per instrument via CC91 (reverb)
and CC93 (chorus). CC value * reverb_wet/chorus_wet = actual wet level."
```
